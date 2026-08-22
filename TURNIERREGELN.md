# Verbindliche Turnierregeln – Siloplanen-Race

Diese Datei ist die zentrale fachliche Quelle für den Turnierablauf. Änderungen
an Auslosung, Zeitplan, Moderation, Zeitmessungszuordnung, Wertung, Ranglisten
und PDF-Ausgaben müssen mit diesen Regeln kompatibel bleiben.

Bei einem Widerspruch zwischen Implementierung, älteren Notizen und dieser
Datei darf die fachliche Logik nicht stillschweigend geändert werden. Eine
Regeländerung muss zuerst ausdrücklich mit den Veranstaltern abgestimmt,
anschließend hier dokumentiert und durch automatische Tests abgesichert werden.

## Grundaufbau

- Es gibt vier Bahnen.
- Jede Mannschaft absolviert zwei Vorrundenläufe.
- Die Zeiten beider Vorrundenläufe werden addiert.
- Die niedrigste vollständige Gesamtzeit erhält Vorrundenrang 1.
- Die nächste Runde darf erst erzeugt werden, wenn alle Vorrundenergebnisse
  vollständig sind.

## Weiterkommen nach der Vorrunde

- Vorrundenplätze 1–8 kommen in das Halbfinale.
- Vorrundenplätze 9 bis N scheiden aus dem Titelbewerb aus und erhalten einen
  Platzierungslauf zur Ermittlung ihres endgültigen Rangs.
- Die acht Halbfinalisten werden zufällig auf zwei Halbfinalläufe mit jeweils
  vier Mannschaften verteilt.

## Platzierungsläufe ab Rang 9

- Die Mannschaften werden in Rangblöcke mit höchstens vier Mannschaften
  eingeteilt.
- Die schlechteste Ranggruppe läuft zuerst, danach folgen die besseren
  Ranggruppen.
- Bei 42 Mannschaften lautet die feste Reihenfolge:
  Plätze 39–42, 35–38, 31–34, 27–30, 23–26, 19–22, 15–18, 11–14 und 9–10.
- Innerhalb eines Platzierungslaufs entscheidet die Laufzeit einschließlich
  eingetragener Strafsekunden über die endgültigen Plätze dieses Rangblocks.
- Ein absolvierter Platzierungslauf ist für diese Mannschaften der Ziellauf;
  sie kommen danach in keine weitere Runde.

## Halbfinale und Finale

- Die Zeiten beider Halbfinalläufe werden gemeinsam gereiht.
- Die vier insgesamt schnellsten Halbfinalzeiten kommen in das große Finale.
- Die übrigen vier Halbfinalisten kommen in das kleine Finale.
- Es gilt ausdrücklich **nicht** „die besten zwei pro Halbfinallauf“.
- Das kleine Finale bestimmt die Plätze 5–8.
- Das große Finale bestimmt die Plätze 1–4.
- Innerhalb des jeweiligen Finales entscheidet die Finalzeit einschließlich
  eingetragener Strafsekunden.

## Verbindliche Laufreihenfolge

Die fachliche Reihenfolge ist eine harte Regel und darf für keine andere
Optimierung verändert werden:

1. Platzierungsläufe, schlechteste Ranggruppe zuerst
2. Halbfinale
3. Kleines Finale
4. Großes Finale

## Pausenregel

- Bei allen automatisch erzeugten Läufen außer den Finalen soll zwischen zwei
  Einsätzen derselben Mannschaft nach Möglichkeit mindestens ein vollständiger
  anderer Lauf liegen.
- Diese Pausenregel ist eine weiche Optimierungsregel.
- Die Pausenregel darf die verbindliche Laufreihenfolge niemals verändern und
  die Erzeugung einer Runde nicht blockieren.
- Ist beides nicht gleichzeitig möglich, hat die Laufreihenfolge Vorrang.
- Kleines und großes Finale sind von der Pausenregel ausgenommen.

## Technische Wertungsregeln

- Die automatische Vorrundenrangliste und die Auswahl der besten acht basiert
  derzeit auf der Summe von `Startplatz.ergebnis_sekunden` der beiden
  Vorrundenläufe.
- Separat in der Strafentabelle erfasste Strafsekunden beeinflussen die
  automatische Auswahl der besten acht derzeit nicht.
- In Platzierungs- und Finalläufen werden Strafsekunden bei der Reihenfolge
  innerhalb des jeweiligen Ziellaufs berücksichtigt.
- Sobald eine Mannschaft einen Platzierungs- oder Finallauf mit Ergebnis
  absolviert hat, ist der daraus berechnete Platz endgültig.
- Mannschaften ohne abgeschlossenen Ziellauf werden nur vorläufig gereiht.

Eine Änderung dieser technischen Wertungsregeln ist eine fachliche
Regeländerung und benötigt vor der Umsetzung eine ausdrückliche Freigabe.

## Schutz bestehender Bewerbe

- Code-Updates dürfen bestehende Startlisten oder Ergebnisse nicht automatisch
  neu auslosen, umsortieren oder löschen.
- Neue Auslosungsregeln greifen nur bei einer bewusst ausgelösten neuen
  Auslosung beziehungsweise Rundenerzeugung.
- Vor Änderungen an der Turnierlogik müssen Tests mindestens Vorrunde,
  Platzierungsläufe, Halbfinale, beide Finale, harte Reihenfolge und weiche
  Pausenregel abdecken.

