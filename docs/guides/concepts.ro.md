# Concepte de Bază

Înțelegerea acestor concepte de bază este esențială pentru a utiliza eficient Ordinaut. Ele formează blocurile de construcție ale oricărei automatizări pe care o creați.

---

### Agent

Un **Agent** este un actor în sistem, identificat printr-un ID unic (UUID) și un token de autentificare. Agenții sunt proprietarii sarcinilor și inițiatorii acțiunilor. Puteți crea agenți diferiți pentru roluri diferite (de exemplu, un `agent-de-raportare`, un `agent-de-procesare-date`) și le puteți acorda permisiuni specifice (scopuri) pentru a controla ce li se permite să facă.

---

### Sarcină (Task)

**Sarcina** este unitatea fundamentală de lucru în Ordinaut. Este un obiect persistent care reunește *ce*, *când* și *cum* se realizează o automatizare.

Un obiect Sarcină conține:
- **Metadate:** Un `titlu` și o `descriere` pentru lizibilitate umană.
- **Programare (Schedule):** Definește *când* ar trebui să ruleze sarcina.
- **Pipeline:** Definește secvența de pași de executat.
- **Politică de Execuție:** Definește *cum* ar trebui să ruleze sarcina, inclusiv `prioritatea`, `reîncercările maxime` și `cheia de concurență`.
- **Proprietate:** Câmpul `created_by` leagă sarcina de un Agent.

---

### Programare (Schedule)

**Programarea** determină când este declanșată o sarcină. Ordinaut oferă un sistem de programare extrem de flexibil care suportă mai multe tipuri de declanșatoare.

| `schedule_kind` | Descriere                                                                                             | Exemplu `schedule_expr`                                     |
|:----------------|:--------------------------------------------------------------------------------------------------------|:------------------------------------------------------------|
| `cron`          | Utilizează sintaxa cron standard cu 5 câmpuri pentru programări recurente.                               | `"0 9 * * 1-5"` (În fiecare zi lucrătoare la 9:00 AM)       |
| `rrule`         | Utilizează Regulile de Recurență RFC-5545 pentru logică calendaristică complexă.                          | `"FREQ=MONTHLY;BYDAY=-1FR"` (În ultima vineri a fiecărei luni) |
| `once`          | Execută sarcina o singură dată la un timestamp specific ISO 8601.                                        | `"2025-12-31T23:59:59Z"`                                  |
| `event`         | Declanșează sarcina atunci când un eveniment corespunzător este publicat în sistem.                       | `"user.email.received"`                                   |

!!! tip "Fusurile Orare sunt Importante"
    Toate programările sunt conștiente de fusul orar. Ar trebui să specificați întotdeauna un nume de `timezone` (de exemplu, `Europe/Chisinau`) în definiția sarcinii pentru a vă asigura că programările se declanșează la ora locală corectă, în special în timpul schimbărilor de oră de vară.

---

### Pipeline

**Pipeline-ul** este inima unei sarcini—este definiția declarativă a muncii care trebuie efectuată. Acesta constă dintr-o listă ordonată de **Pași**.

- **Flux de Date:** Rezultatul unui pas poate fi folosit ca intrare pentru pașii ulteriori, permițându-vă să înlănțuiți operațiunile.
- **Parametri:** Pipeline-urile pot primi date inițiale din obiectul `payload.params` din definiția sarcinii.
- **Logică Condiționată:** Pașii pot fi executați condiționat pe baza rezultatului pașilor anteriori.

---

### Pas (Step)

Un **Pas** este o acțiune unică, atomică, în cadrul unui pipeline. Fiecare pas are mai multe proprietăți cheie:

- `id`: Un identificator unic pentru pas în cadrul pipeline-ului.
- `uses`: Adresa **Instrumentului (Tool)** care trebuie executat (de exemplu, `telegram.send_message`).
- `with`: Un obiect care conține argumentele de transmis instrumentului. Această secțiune suportă variabile șablon.
- `save_as`: Un nume sub care va fi salvat rezultatul pasului. Acest lucru face ca rezultatul să fie disponibil pentru pașii ulteriori prin contextul `steps`.
- `if`: O expresie condiționată care determină dacă pasul ar trebui să ruleze.

---

### Instrument (Tool)

Un **Instrument** este o capacitate înregistrată, reutilizabilă, care poate fi apelată dintr-un pas de pipeline. Fiecare instrument are o **schemă de intrare (input schema)** și o **schemă de ieșire (output schema)** strict definite, ceea ce asigură că datele care circulă prin pipeline sunt previzibile și valide. Ordinaut poate fi extins cu instrumente care se conectează la orice API sau serviciu extern.

---

### Rulare (Run)

O **Rulare** este o înregistrare a unei singure execuții a pipeline-ului unei sarcini. De fiecare dată când o sarcină este declanșată de programarea sa sau de un eveniment, se creează un nou obiect Rulare. Acest obiect urmărește:

- Ora de începere și de sfârșit a execuției.
- Starea finală (`succes` sau `eșec`).
- Numărul de `încercări` de reexecutare.
- `Rezultatul` detaliat al pipeline-ului, inclusiv rezultatele fiecărui pas.
- Orice `eroare` care a apărut.

Acest lucru oferă un istoric complet și auditabil al fiecărei acțiuni pe care o întreprinde sistemul.

---

### Coada `due_work`

Aceasta este o tabelă internă a bazei de date care acționează ca o coadă de sarcini. Singura treabă a **Scheduler-ului** este să calculeze următoarea oră de rulare pentru fiecare sarcină și să insereze un rând corespunzător în tabela `due_work`. **Workerii** interoghează apoi această tabelă, preiau în siguranță sarcini folosind `FOR UPDATE SKIP LOCKED` și le execută. Această decuplare a programării de execuție este fundamentală pentru fiabilitatea și scalabilitatea Ordinaut.
