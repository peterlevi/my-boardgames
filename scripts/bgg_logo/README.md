# The "Powered by BGG" logo

BGG's XML API terms ask every public page that shows their data to display
the "Powered by BGG" logo, linked back to BoardGameGeek, sized so its text
stays easily legible. Download one of the official files from
<https://boardgamegeek.com/using_the_xml_api> and save it here as
`powered-by-bgg.svg` (or `.png` / `.webp`).

`report.py` inlines it into the page beside "Open on BGG". Without the file
it prints a warning and credits BGG in plain text instead.
