# Programarea Sarcinilor

Ordinaut oferă un sistem de programare flexibil și puternic care suportă mai multe metode pentru a defini când ar trebui să ruleze o sarcină.

---

## Programare cu RRULE

Pentru cea mai complexă programare, conștientă de calendar, Ordinaut utilizează standardul **RFC 5545 Recurrence Rule (RRULE)**.

Setați `schedule_kind` la `rrule` pentru a utiliza această metodă.

### Exemple Comune de RRULE

| Caz de Utilizare                               | Expresie RRULE                                         |
|:-----------------------------------------------|:-------------------------------------------------------|
| În fiecare zi lucrătoare la 8:30 AM            | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30`  |
| În ultima vineri a fiecărei luni la 5:00 PM    | `FREQ=MONTHLY;BYDAY=FR;BYSETPOS=-1;BYHOUR=17`            |
| Anual pe 15 iunie                              | `FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=15`                    |

### Fusuri Orare și Ora de Vară (DST)

Procesarea RRULE în Ordinaut este complet conștientă de fusul orar. Este **critic** să furnizați un nume de `timezone` valid (de exemplu, `Europe/Chisinau`).

---

## Programare cu Cron

Pentru programarea tradițională, bazată pe timp, Ordinaut suportă expresii cron standard cu 5 câmpuri.

Setați `schedule_kind` la `cron` pentru a utiliza această metodă.

### Formatul Expresiei Cron

`minut oră zi_luna luna zi_saptamana`

### Exemplu de Sarcină Cron

```json
{
  "title": "Curățenie Orară a Sistemului",
  "schedule_kind": "cron",
  "schedule_expr": "0 * * * *",
  "timezone": "UTC",
  "payload": { ... }
}
```

---

## Programare Unică (`once`)

Pentru a programa o sarcină să ruleze exact o singură dată la un moment specific în viitor, utilizați `once`.

### Formatul Expresiei `once`

`schedule_expr` trebuie să fie un timestamp în format **ISO 8601**.

### Exemplu de Sarcină Unică

```json
{
  "title": "Implementare Funcționalitate Nouă",
  "schedule_kind": "once",
  "schedule_expr": "2025-12-25T09:00:00+02:00",
  "timezone": "Europe/Chisinau",
  "payload": { ... }
}
```
