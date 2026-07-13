# CRM locale per lead digitali

Questa app crea un piccolo gestionale locale per trovare, qualificare e seguire aziende a cui proporre siti, restyling e presenza social.

## Avvio

Da questa cartella:

```bash
python3 server.py --open
```

Oppure su macOS puoi aprire `start_crm.command`.

L'app usa un database SQLite locale in:

```text
data/crm.sqlite3
```

## Cosa include

- Database lead, contatti, attivita, follow-up e scansioni sito.
- Dashboard commerciale.
- Pipeline lead.
- Import CSV ed export CSV.
- Scanner sito con punteggio opportunita.
- Generatore messaggi personalizzati.
- Categorie automatiche: nessun sito, sito critico, sito migliorabile, social debole.
- Lead Finder automatico per zona e settore tramite OpenStreetMap/Overpass, con import automatico dei lead senza sito e con almeno un canale di contatto.

## Nota operativa

Il CRM e pensato per lavorare in modo pulito: conserva le fonti, gestisce contatti da verificare e usa messaggi approvati manualmente prima dell'invio.

Il finder non effettua scraping diretto di Google Maps. Per quel livello conviene collegare un provider ufficiale o con licenza, per esempio Google Places API o SerpAPI, e usare OpenStreetMap come base gratuita di partenza.

Di default il CRM esclude i risultati senza telefono, email o social: un'azienda senza canale di contatto non viene trattata come lead commerciale.
