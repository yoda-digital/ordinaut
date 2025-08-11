# Scheduling with RRULE

Ordinaut uses the powerful **RFC 5545 Recurrence Rule (RRULE)** standard for all complex, calendar-aware scheduling. This allows you to define sophisticated schedules that go far beyond what traditional cron expressions can support.

When creating a task, set the `schedule_kind` to `rrule` and provide the rule string in `schedule_expr`.

## Common RRULE Examples

Here are some practical examples you can use in your tasks.

| Use Case                                  | RRULE Expression                                       |
|:------------------------------------------|:-------------------------------------------------------|
| Every weekday at 8:30 AM                  | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30`  |
| Every other Monday at 10:00 AM            | `FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;BYHOUR=10`              |
| The last Friday of every month at 5:00 PM | `FREQ=MONTHLY;BYDAY=FR;BYSETPOS=-1;BYHOUR=17`            |
| The first day of every quarter at 9:00 AM | `FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=9`          |
| Annually on June 15th                     | `FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=15`                    |
| Twice a day (9 AM and 6 PM)               | `FREQ=DAILY;BYHOUR=9,18`                                 |

## Key RRULE Components

An RRULE string is a semicolon-separated list of properties.

- **`FREQ`**: The base frequency of the recurrence. (e.g., `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`).
- **`INTERVAL`**: Works with `FREQ` to specify intervals. `FREQ=WEEKLY;INTERVAL=2` means every two weeks.
- **`BYDAY`**: Specifies the days of the week (`MO`, `TU`, `WE`, `TH`, `FR`, `SA`, `SU`).
- **`BYMONTHDAY`**: Specifies the day of the month (e.g., `1`, `15`, `-1` for the last day).
- **`BYMONTH`**: Specifies the month of the year (1-12).
- **`BYHOUR`**, **`BYMINUTE`**, **`BYSECOND`**: Specifies the time of day.
- **`BYSETPOS`**: Used with other `BY` rules to select a specific occurrence from the generated set. `BYSETPOS=-1` is how you select the *last* occurrence in a period.

## Timezones and DST

RRULE processing in Ordinaut is fully timezone-aware. It is **critical** to provide a valid `timezone` name (e.g., `Europe/Chisinau`) in your task definition. The system uses this timezone to:

- Correctly interpret the start time of the rule.
- Handle Daylight Saving Time (DST) transitions automatically, ensuring your tasks run at the correct local time year-round.
- Calculate all future occurrences accurately.

### Example Task with RRULE

```json
{
  "title": "Monthly Financial Report",
  "description": "Generate the financial report on the last business day of the month.",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;BYHOUR=17;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": { ... },
  "created_by": "..."
}
```

This task will reliably run at 5:00 PM on the last weekday of every month, regardless of whether that day is the 28th, 29th, 30th, or 31st, and it will correctly adjust for DST.
