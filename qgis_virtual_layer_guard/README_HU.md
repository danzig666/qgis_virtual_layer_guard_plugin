# Virtuális rétegőr (Virtual Layer Guard)

QGIS 3.30 – 4.x plugin, amely megakadályozza, hogy a virtuális rétegek (és más,
függőséggel rendelkező rétegek) csendben eltűnjenek a projektfájlból.

## A hiba, amit kivéd

Minden rétegnek lehetnek *függőségei* (a projektfájlban `<layerDependencies>` /
`<dataDependencies>`). A virtuális rétegeknek mindig van függőségük: azok a
rétegek, amelyekből a lekérdezésük olvas.

Ha a projektben **egyetlen** réteg is olyan layer ID-tól függ, amely már nem
létezik (réteg törlése vagy cseréje, adatforrás-csere, projektek közti
rétegmozgatás után), a QGIS betöltéskor **az összes** függőséggel rendelkező
réteget kihagyja, hibaüzenet nélkül:

- a Rétegek panelen a nevük megmarad, de mögöttük nincs réteg,
- a **következő mentés véglegesen törli** a definíciójukat a projektfájlból
  (SQL-lekérdezés, stílus, join-ok, címkék).

## Mit csinál a plugin

- **Mentéskor** törli a nem létező rétegekre mutató függőségi bejegyzéseket,
  így a hiba oka meg sem marad a fájlban.
- **Mentéskor** visszaírja azoknak a rétegeknek a definícióját, amelyeknek csak
  rétegfa-bejegyzésük van (ezeket a QGIS kihagyná).
- **Megnyitáskor** észreveszi, ha a QGIS kihagyott rétegeket a projektfájlból,
  és automatikusan visszatölti őket. Utána a projektet menteni kell.
- **Minden mentéskor** másolatot tart minden virtuális rétegdefinícióról
  (`<QGIS profil>/virtual_layer_guard/`). Ha egy régebbi mentésből már
  kiestek, az *Elveszett rétegek visszaállítása* menüponttal visszahozhatók.
- **Figyelmeztet**, ha
  - olyan réteget törölsz, amelyből virtuális réteg olvas (a törölt rétegre
    mutató függőségeket azonnal el is távolítja),
  - egy réteg adatforrásának cseréje után egy rá épülő virtuális réteg hibás
    lesz (a hibaüzenettel együtt),
  - olyan virtuális réteg kerül a projektbe, amely itt nem létező rétegre
    hivatkozik.

## Menü

*Modulok → Virtual Layer Guard*

- **Projekt rétegeinek ellenőrzése**: lista a definíció nélküli rétegfa-bejegyzésekről,
  a nem létező rétegre mutató függőségekről, a hibás virtuális rétegekről és a
  hiányzó rétegre hivatkozó virtuális rétegekről.
- **Elveszett rétegek visszaállítása**: a mentett másolatokból visszatölti a
  definíció nélküli rétegfa-bejegyzések rétegeit, az eredeti layer ID-val.

## Korlátok

- A visszaállítás csak akkor működik, ha a réteg definíciója valahol megvan:
  a megnyitott projektfájlban, vagy a plugin egy korábbi mentéskor készített
  másolatában.
- A plugin nem javítja az SQL-lekérdezéseket. Ha a forrásrétegből hiányzik egy
  mező, amelyet a lekérdezés használ, a virtuális réteg hibás marad, de a
  definíciója nem vész el.
