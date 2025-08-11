# Programare cu RRULE

Ordinaut utilizează standardul puternic **RFC 5545 Recurrence Rule (RRULE)** pentru toate programările complexe, conștiente de calendar. Acest lucru vă permite să definiți programe sofisticate care depășesc cu mult ceea ce pot suporta expresiile cron tradiționale.

Când creați o sarcină, setați `schedule_kind` la `rrule` și furnizați șirul regulii în `schedule_expr`.

## Exemple Comune de RRULE

Iată câteva exemple practice pe care le puteți utiliza în sarcinile dumneavoastră.

| Caz de Utilizare                               | Expresie RRULE                                         |
|:-----------------------------------------------|:-------------------------------------------------------|
| În fiecare zi lucrătoare la 8:30 AM            | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30`  |
| O dată la două luni, lunea la 10:00 AM         | `FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;BYHOUR=10`              |
| În ultima vineri a fiecărei luni la 5:00 PM    | `FREQ=MONTHLY;BYDAY=FR;BYSETPOS=-1;BYHOUR=17`            |
| În prima zi a fiecărui trimestru la 9:00 AM    | `FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=9`          |
| Anual pe 15 iunie                              | `FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=15`                    |
| De două ori pe zi (9 AM și 6 PM)               | `FREQ=DAILY;BYHOUR=9,18`                                 |

## Componente Cheie ale RRULE

Un șir RRULE este o listă de proprietăți separate prin punct și virgulă.

- **`FREQ`**: Frecvența de bază a recurenței (de exemplu, `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`).
- **`INTERVAL`**: Funcționează cu `FREQ` pentru a specifica intervale. `FREQ=WEEKLY;INTERVAL=2` înseamnă o dată la două săptămâni.
- **`BYDAY`**: Specifică zilele săptămânii (`MO`, `TU`, `WE`, `TH`, `FR`, `SA`, `SU`).
- **`BYMONTHDAY`**: Specifică ziua lunii (de exemplu, `1`, `15`, `-1` pentru ultima zi).
- **`BYMONTH`**: Specifică luna anului (1-12).
- **`BYHOUR`**, **`BYMINUTE`**, **`BYSECOND`**: Specifică ora din zi.
- **`BYSETPOS`**: Folosit cu alte reguli `BY` pentru a selecta o anumită ocurență din setul generat. `BYSETPOS=-1` este modul în care selectați *ultima* ocurență dintr-o perioadă.

## Fusuri Orare și Ora de Vară (DST)

Procesarea RRULE în Ordinaut este complet conștientă de fusul orar. Este **critic** să furnizați un nume de `timezone` valid (de exemplu, `Europe/Chisinau`) în definiția sarcinii dumneavoastră. Sistemul folosește acest fus orar pentru a:

- Interpreta corect ora de începere a regulii.
- Gestiona automat tranzițiile la ora de vară (DST), asigurându-vă că sarcinile dumneavoastră rulează la ora locală corectă pe tot parcursul anului.
- Calcula cu precizie toate ocurențele viitoare.

### Exemplu de Sarcină cu RRULE

```json
{
  "title": "Raport Financiar Lunar",
  "description": "Generează raportul financiar în ultima zi lucrătoare a lunii.",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;BYHOUR=17;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": { ... },
  "created_by": "..."
}
```

Această sarcină va rula în mod fiabil la ora 17:00 în ultima zi lucrătoare a fiecărei luni, indiferent dacă acea zi este 28, 29, 30 sau 31, și se va ajusta corect pentru ora de vară.