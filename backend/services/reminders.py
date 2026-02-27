from firebase_client import get_db
from utils.user_data import get_active_users
from utils.fcm import get_fcm_token, send_fcm_message
from logger import logger
from datetime import datetime, timezone
import asyncio
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

POLL_WINDOW_SECONDS = 60  # Deliver reminders due within this window

def _parse_user_timezone(uid: str, db) -> str:
    """Read user's timezone from Firestore config/device doc."""
    try:
        doc = db.document(f'users/{uid}/config/device').get()
        if doc.exists:
            return doc.to_dict().get('timezone', 'UTC')
    except Exception as e:
        logger.error(f"Error reading timezone for {uid}: {e}")
    return 'UTC'

def _calculate_next_recurrence(current_iso: str, rule: str, tz: str) -> str | None:
    """Advance a reminder time by recurrence rule. Returns new ISO string or None."""
    r = rule.lower().strip()
    try:
        dt = datetime.fromisoformat(current_iso)
    except ValueError:
        return None

    if r in ('daily', 'day'):
        from datetime import timedelta
        dt += timedelta(days=1)
    elif r in ('weekly', 'week'):
        from datetime import timedelta
        dt += timedelta(weeks=1)
    elif r in ('monthly', 'month'):
        month = dt.month % 12 + 1
        year = dt.year + (1 if dt.month == 12 else 0)
        try:
            dt = dt.replace(year=year, month=month)
        except ValueError:
            # Handle months with fewer days
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            dt = dt.replace(year=year, month=month, day=min(dt.day, last_day))
    elif r in ('yearly', 'year'):
        try:
            dt = dt.replace(year=dt.year + 1)
        except ValueError:
            dt = dt.replace(year=dt.year + 1, day=28)  # Feb 29 edge case
    else:
        # Parse "N unit" format, e.g. "2 days", "30 minutes"
        parts = r.split(' ')
        if len(parts) == 2:
            try:
                val = int(parts[0])
            except ValueError:
                return None
            unit = parts[1]
            from datetime import timedelta
            if unit.startswith('min'):
                dt += timedelta(minutes=val)
            elif unit.startswith('hour'):
                dt += timedelta(hours=val)
            elif unit.startswith('day'):
                dt += timedelta(days=val)
            elif unit.startswith('week'):
                dt += timedelta(weeks=val)
            elif unit.startswith('month'):
                month = (dt.month - 1 + val) % 12 + 1
                year = dt.year + (dt.month - 1 + val) // 12
                try:
                    dt = dt.replace(year=year, month=month)
                except ValueError:
                    import calendar
                    last_day = calendar.monthrange(year, month)[1]
                    dt = dt.replace(year=year, month=month, day=min(dt.day, last_day))
            else:
                return None
        else:
            return None

    return dt.isoformat()

async def _process_reminders(uid: str, db, fcm_token: str, user_tz: str):
    """Check and deliver due reminders for a user."""
    try:
        now_utc = datetime.now(timezone.utc)
        try:
            tz = ZoneInfo(user_tz)
        except Exception:
            tz = ZoneInfo('UTC')
        now_local = now_utc.astimezone(tz)

        reminders_ref = db.collection(f'users/{uid}/reminders')
        docs = reminders_ref.stream()

        for doc in docs:
            data = doc.to_dict()
            reminder_time_str = data.get('reminderTime')
            if not reminder_time_str:
                continue

            last_sent = data.get('lastSent')
            if last_sent == reminder_time_str:
                continue

            try:
                reminder_dt = datetime.fromisoformat(reminder_time_str)
                # Treat as local time in user's timezone if naive
                if reminder_dt.tzinfo is None:
                    reminder_dt = reminder_dt.replace(tzinfo=tz)
            except ValueError:
                continue

            # Check if due (within poll window)
            diff_seconds = (now_local - reminder_dt).total_seconds()
            if diff_seconds < -POLL_WINDOW_SECONDS:
                continue  # Not due yet

            title = data.get('title', 'Reminder')
            content = data.get('content', '')
            recurrence = data.get('recurrenceRule')

            # Send FCM
            send_fcm_message(fcm_token, {
                "type": "reminder",
                "reminderId": str(doc.id),
                "title": str(title),
                "content": str(content) if content else "",
                "reminderTime": str(reminder_time_str),
            }, notification={
                "title": f"🔔 {title}",
                "body": content or "Reminder"
            })
            logger.info(f"Sent reminder FCM to {uid}: {title}")

            # Advance recurrence or mark as delivered
            if recurrence:
                next_time = _calculate_next_recurrence(reminder_time_str, recurrence, user_tz)
                if next_time:
                    doc.reference.update({"reminderTime": next_time, "lastSent": reminder_time_str})
                    logger.debug(f"Advanced recurring reminder {doc.id} to {next_time}")
                else:
                    doc.reference.update({"lastSent": reminder_time_str})
                    logger.debug(f"Marked reminder {doc.id} as sent (invalid recurrence)")
            else:
                doc.reference.update({"lastSent": reminder_time_str})
                logger.debug(f"Marked one-off reminder {doc.id} as sent")

    except Exception as e:
        logger.error(f"Error processing reminders for {uid}: {e}")

async def _process_mood_reminder(uid: str, db, fcm_token: str, user_tz: str):
    """Check and send mood daily reminder if due."""
    try:
        now_utc = datetime.now(timezone.utc)
        try:
            tz = ZoneInfo(user_tz)
        except Exception:
            tz = ZoneInfo('UTC')
        now_local = now_utc.astimezone(tz)

        # Read mood config from synced eventTypes store (or moodStore)
        mood_doc = db.document(f'users/{uid}/sync/moodStore').get()
        if not mood_doc.exists:
            return

        mood_data = mood_doc.to_dict()
        import json
        if 'data' in mood_data and isinstance(mood_data['data'], str):
            try:
                parsed = json.loads(mood_data['data'])
                mood_data = parsed.get('state', parsed)
            except json.JSONDecodeError:
                pass

        if not mood_data.get('moodReminderEnabled'):
            return

        reminder_time_str = mood_data.get('moodReminderTime')
        if not reminder_time_str:
            return

        try:
            reminder_dt = datetime.fromisoformat(reminder_time_str)
        except ValueError:
            return

        # Check if current H:M matches (within poll window)
        target_today = now_local.replace(
            hour=reminder_dt.hour, minute=reminder_dt.minute, second=0, microsecond=0
        )
        diff = abs((now_local - target_today).total_seconds())
        if diff > POLL_WINDOW_SECONDS:
            return

        # Check if already logged today
        today_str = now_local.strftime('%Y-%m-%d')
        moods = mood_data.get('moods', {})
        if today_str in moods:
            return

        # Check dedup: don't send twice today
        state_doc = db.document(f'users/{uid}/config/reminderState').get()
        if state_doc.exists:
            state_data = state_doc.to_dict()
            last_mood_sent = state_data.get('lastMoodReminderDate', '')
            if last_mood_sent == today_str:
                return

        # Send FCM
        send_fcm_message(fcm_token, {
            "type": "mood_daily",
            "date": str(today_str),
        }, notification={
            "title": "How was your day?",
            "body": "Take a moment to evaluate your day and add a note."
        })
        logger.info(f"Sent mood reminder FCM to {uid}")

        # Mark as sent
        db.document(f'users/{uid}/config/reminderState').set(
            {"lastMoodReminderDate": today_str}, merge=True
        )

    except Exception as e:
        logger.error(f"Error processing mood reminder for {uid}: {e}")

async def _process_range_notifications(uid: str, db, fcm_token: str, user_tz: str):
    """Check and send time range start notifications if due."""
    try:
        now_utc = datetime.now(timezone.utc)
        try:
            tz = ZoneInfo(user_tz)
        except Exception:
            tz = ZoneInfo('UTC')
        now_local = now_utc.astimezone(tz)

        # Read event types store (contains ranges)
        et_doc = db.document(f'users/{uid}/sync/eventTypes').get()
        if not et_doc.exists:
            return

        et_data = et_doc.to_dict()
        import json
        if 'data' in et_data and isinstance(et_data['data'], str):
            try:
                parsed = json.loads(et_data['data'])
                et_data = parsed.get('state', parsed)
            except json.JSONDecodeError:
                return

        ranges = et_data.get('ranges', [])
        if not ranges:
            return

        current_dow = now_local.weekday()
        js_dow = (current_dow + 1) % 7  # Convert Python weekday (Mon=0) to JS weekday (Sun=0)

        for r in ranges:
            if not r.get('isEnabled'):
                continue
            if js_dow not in r.get('days', []):
                continue

            start = r.get('start', {})
            start_hour = start.get('hour', 0)
            start_minute = start.get('minute', 0)

            target = now_local.replace(
                hour=start_hour, minute=start_minute, second=0, microsecond=0
            )
            diff = abs((now_local - target).total_seconds())
            if diff > POLL_WINDOW_SECONDS:
                continue

            # Dedup: check if already sent today for this range
            range_id = r.get('id', '')
            dedup_key = f"range_{range_id}_{now_local.strftime('%Y%m%d')}"
            state_doc = db.document(f'users/{uid}/config/reminderState').get()
            if state_doc.exists:
                sent_ranges = state_doc.to_dict().get('sentRanges', [])
                if dedup_key in sent_ranges:
                    continue

            # Send FCM
            title = r.get('title', 'Time Range')
            send_fcm_message(fcm_token, {
                "type": "range_start",
                "rangeId": str(range_id),
                "title": str(title),
            }, notification={
                "title": title,
                "body": "Starting now"
            })
            logger.info(f"Sent range start FCM to {uid}: {title}")

            # Mark as sent
            from firebase_admin import firestore as fs
            db.document(f'users/{uid}/config/reminderState').set(
                {"sentRanges": fs.ArrayUnion([dedup_key])}, merge=True
            )

    except Exception as e:
        logger.error(f"Error processing range notifications for {uid}: {e}")

async def run_reminders_job():
    """Main polling job — runs every 30s via APScheduler."""
    logger.debug("Running reminders job...")
    try:
        db = get_db()
        users = await asyncio.to_thread(get_active_users, db)

        for uid, settings in users:
            fcm_token = get_fcm_token(uid, db)
            if not fcm_token:
                continue

            user_tz = _parse_user_timezone(uid, db)

            await _process_reminders(uid, db, fcm_token, user_tz)
            await _process_mood_reminder(uid, db, fcm_token, user_tz)
            await _process_range_notifications(uid, db, fcm_token, user_tz)

    except Exception as e:
        logger.error(f"Error in reminders job: {e}")
