# Pipeline-uri și Instrumente

Puterea Ordinaut provine din motorul său declarativ de pipeline, care execută o serie de pași într-un mod previzibil și fiabil.

## Structura Pipeline-ului

Un pipeline este un tablou JSON de **pași** definiți în `payload`-ul unei Sarcini. Motorul procesează acești pași în ordine, transmițând contextul între ei.

```json
{
  "payload": {
    "params": { "city": "Chisinau" },
    "pipeline": [
      {
        "id": "get_weather",
        "uses": "weather-api.get_forecast",
        "with": {"location": "${params.city}"},
        "save_as": "weather"
      },
      {
        "id": "send_alert",
        "uses": "telegram.send_message",
        "if": "steps.weather.temperature > 25",
        "with": {
          "message": "Astăzi este cald: ${steps.weather.temperature}°C"
        }
      }
    ]
  }
}
```

### Proprietăți Cheie ale Pașilor

- `id`: Un identificator unic pentru pas în cadrul pipeline-ului.
- `uses`: Adresa **Instrumentului** de executat (de exemplu, `weather-api.get_forecast`).
- `with`: Un obiect care conține argumentele pentru instrument. Această secțiune suportă variabile șablon.
- `save_as`: Cheia sub care va fi salvat rezultatul pasului în context. Acest lucru permite pașilor ulteriori să utilizeze rezultatul (de exemplu, `steps.weather`).
- `if`: O expresie condițională [JMESPath](https://jmespath.org/). Dacă se evaluează la o valoare "falsy" (cum ar fi `false`, `null`, `[]`, `{}`), pasul este omis.
- `timeout_seconds`: Un timeout opțional pentru apelul instrumentului (implicit este 30 de secunde).
- `max_retries`: Un număr opțional de reîncercări pentru acest pas specific în caz de eșec.

## Variabile Șablon

Puteți insera dinamic date în blocul `with` folosind variabile șablon, care sunt rezolvate folosind expresii JMESPath în raport cu contextul curent.

- **`${params.variable_name}`**: Accesează parametrii definiți în secțiunea `payload.params` a sarcinii.
- **`${steps.step_id.output_field}`**: Accesează rezultatul unui pas anterior care a folosit `save_as`. Puteți traversa obiecte JSON imbricate (de exemplu, `${steps.weather.details.humidity}`).
- **`${now}`**: O variabilă specială care furnizează timestamp-ul UTC curent în format ISO 8601.

## Catalogul de Instrumente

Instrumentele sunt blocurile de construcție ale pipeline-urilor. Ele reprezintă o capacitate specifică, cum ar fi trimiterea unui e-mail sau interogarea unei baze de date. Fiecare instrument este definit într-un catalog central și are un contract strict:

- **Adresă:** Un identificator unic, lizibil pentru om (de exemplu, `google-calendar.list_events`).
- **Schemă de Intrare:** O Schemă JSON care definește argumentele așteptate. Motorul de pipeline validează blocul `with` al unui pas în raport cu această schemă înainte de execuție.
- **Schemă de Ieșire:** O Schemă JSON care definește rezultatul așteptat. Motorul validează răspunsul instrumentului în raport cu această schemă după execuție.

Această abordare bazată pe scheme asigură că toate interacțiunile sunt previzibile, validate și sigure din punct de vedere al tipului, ceea ce este critic pentru construirea de automatizări robuste.

## Gestionarea Erorilor

Dacă un pas eșuează (de exemplu, un apel la un instrument expiră sau returnează o eroare), motorul va respecta politica `max_retries` definită în sarcină sau în pasul însuși. Dacă toate reîncercările eșuează, întreaga rulare a pipeline-ului este marcată ca `eșuată`, iar detaliile erorii sunt înregistrate în obiectul **Rulare**.
