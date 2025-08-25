# Concepte de Bază

Înțelegerea acestor concepte de bază este esențială pentru a utiliza eficient Ordinaut. Ele formează blocurile de construcție ale oricărei automatizări pe care o creați.

---

### Agent

Un **Agent** este un actor în sistem, identificat printr-un ID unic (UUID) și un token de autentificare. Agenții sunt proprietarii sarcinilor și inițiatorii acțiunilor.

---

### Sarcină (Task)

**Sarcina** este unitatea fundamentală de lucru în Ordinaut. Este un obiect persistent care reunește *ce*, *când* și *cum* se realizează o automatizare.

O Sarcină conține:
- **Metadate:** Un `title` și `description`.
- **Programare:** Definește *când* ar trebui să ruleze sarcina, folosind `schedule_kind` (`cron`, `rrule`, `once`, `event`) și `schedule_expr`.
- **Pipeline:** `payload`-ul definește secvența de pași de executat.
- **Politică de Execuție:** Definește *cum* ar trebui să ruleze sarcina, inclusiv `priority`, `max_retries`, `backoff_strategy` și `concurrency_key`.
- **Proprietate:** Câmpul `created_by` leagă sarcina de un Agent.

---

### Declanșatoare de Execuție a Sarcinilor

Ordinaut oferă mai multe mecanisme de declanșare:

- **Declanșatoare Temporale (`cron`, `rrule`, `once`):** Gestionate intern de serviciul APScheduler.
- **Declanșatoare pe Evenimente (`event`):** Declanșate când un sistem extern publică un eveniment la endpoint-ul API `/events`.
- **Declanșatoare Condiționale (`condition`):** Destinate să fie declanșate de sisteme externe care monitorizează condiții specifice.
- **Declanșatoare Manuale:** Orice sarcină poate fi rulată imediat printr-un apel API `POST /tasks/{id}/run_now`.

---

### Pipeline

**Pipeline-ul** este inima unei sarcini—este definiția declarativă a muncii care trebuie efectuată, specificată în câmpul `payload`. Acesta constă dintr-o listă ordonată de **Pași**.

---

### Pas (Step)

Un **Pas** este o acțiune unică, atomică, în cadrul unui pipeline. Fiecare pas are mai multe proprietăți cheie:

- `id`: Un nume unic pentru pas.
- `uses`: Adresa **Instrumentului (Tool)** de executat.
- `with`: Argumentele pentru instrument.
- `save_as`: O cheie pentru a stoca rezultatul pasului.
- `if`: O expresie condiționată pentru a determina dacă pasul ar trebui să ruleze.

---

### Instrument (Tool)

Un **Instrument** reprezintă o capacitate specifică, reutilizabilă, care poate fi apelată dintr-un pas de pipeline (de exemplu, trimiterea unui e-mail).

!!! warning "Execuția Instrumentelor este Simulată"
    Este crucial să înțelegeți că motorul de bază Ordinaut **simulează execuția instrumentelor**. Când un pas cu un câmp `uses` este procesat, motorul recunoaște pasul, redă șabloanele de intrare și generează un rezultat simulat. **Nu** execută niciun cod real pentru instrument.

    Implementarea efectivă a instrumentelor trebuie construită ca **servicii de extensie separate**.

---

### Rulare (Run)

O **Rulare** este o înregistrare a unei singure execuții a pipeline-ului unei sarcini. Urmărește ora de începere/sfârșit, starea (`succes` sau `eșec`), numărul de `încercări` și `rezultatul` detaliat.

---

### Coada `due_work`

Aceasta este o tabelă internă a bazei de date care acționează ca o coadă de joburi. **Scheduler-ul** adaugă joburi aici, iar **Workerii** le preiau în siguranță folosind `FOR UPDATE SKIP LOCKED` pentru a le executa. Această decuplare este fundamentală pentru fiabilitatea sistemului.