# Scheduling Tasks

Ordinaut provides a flexible and powerful scheduling system that supports several methods for defining when a task should run. You can choose the method that best fits your needs, from simple one-time executions to complex, calendar-aware recurring schedules.

When creating a task, you specify the scheduling method using the `schedule_kind` field and provide the corresponding expression in `schedule_expr`.

---

## RRULE Scheduling

For the most complex, calendar-aware scheduling, Ordinaut uses the powerful **RFC 5545 Recurrence Rule (RRULE)** standard. This allows you to define sophisticated schedules that go far beyond what traditional cron expressions can support.

Set `schedule_kind` to `rrule` to use this method.

### Common RRULE Examples

| Use Case                                  | RRULE Expression                                       |
|:------------------------------------------|:-------------------------------------------------------|
| Every weekday at 8:30 AM                  | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30`  |
| Every other Monday at 10:00 AM            | `FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;BYHOUR=10`              |
| The last Friday of every month at 5:00 PM | `FREQ=MONTHLY;BYDAY=FR;BYSETPOS=-1;BYHOUR=17`            |
| The first day of every quarter at 9:00 AM | `FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=9`          |
| Annually on June 15th                     | `FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=15`                    |
| Twice a day (9 AM and 6 PM)               | `FREQ=DAILY;BYHOUR=9,18`                                 |

### Key RRULE Components

An RRULE string is a semicolon-separated list of properties like `FREQ`, `INTERVAL`, `BYDAY`, `BYMONTH`, `BYHOUR`, etc.

### Timezones and DST

RRULE processing in Ordinaut is fully timezone-aware. It is **critical** to provide a valid `timezone` name (e.g., `Europe/Chisinau`) in your task definition to ensure schedules handle Daylight Saving Time (DST) transitions correctly.

---

## Cron Scheduling

For traditional, time-based scheduling, Ordinaut supports standard 5-field cron expressions.

Set `schedule_kind` to `cron` to use this method.

### Cron Expression Format

The format is a string with five fields separated by spaces:

`* * * * *`

- **Minute** (0-59)
- **Hour** (0-23)
- **Day of Month** (1-31)
- **Month** (1-12)
- **Day of Week** (0-6, where Sunday is 0 and 6, or use names like SUN, MON)

### Example Cron Task

```json
{
  "title": "Hourly System Cleanup",
  "description": "Run a cleanup script at the beginning of every hour.",
  "schedule_kind": "cron",
  "schedule_expr": "0 * * * *",
  "timezone": "UTC",
  "payload": { ... },
  "created_by": "..."
}
```

---

## One-Time Scheduling

To schedule a task to run exactly once at a specific time in the future, you can use the `once` schedule kind.

Set `schedule_kind` to `once` to use this method.

### `once` Expression Format

The `schedule_expr` for a one-time task must be a timestamp in **ISO 8601 format**.

### Example One-Time Task

```json
{
  "title": "Deploy New Feature",
  "description": "Trigger the deployment pipeline at a specific time.",
  "schedule_kind": "once",
  "schedule_expr": "2025-12-25T09:00:00+02:00",
  "timezone": "Europe/Chisinau",
  "payload": { ... },
  "created_by": "..."
}
```

This task will execute a single time on Christmas Day 2025 at 9:00 AM in the Chișinău timezone.