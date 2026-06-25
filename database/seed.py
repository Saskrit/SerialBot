SERIALS = [
  {
    "name": "Anupamaa",
    "slug": "anupamaa",
    "aliases": ["anupama", "anup", "anupamaa star plus"],
  },
  {
    "name": "Udne Ki Aasha",
    "slug": "udne-ki-aasha",
    "aliases": ["udne", "udne ki asha", "ukia"],
  },
  {
    "name": "Yeh Rishta Kya Kehlata Hai",
    "slug": "yrkkh",
    "aliases": ["yrkkh", "rishta", "yeh rishta", "yrkk"],
  },
  {
    "name": "Sairaab",
    "slug": "sairaab",
    "aliases": ["sairab", "saira"],
  },
  {
    "name": "O Humnava Tum Dena Saath Mera",
    "slug": "o-humnava",
    "aliases": ["humnava", "o humnava"],
  },
  {
    "name": "Mr and Mrs Parshuram",
    "slug": "mr-mrs-parshuram",
    "aliases": ["parshuram", "mr mrs parshuram"],
  },
  {
    "name": "Kyunki Saas Bhi Kabhi Bahu Thi 2",
    "slug": "kyunki-saas-2",
    "aliases": ["kyunki saas", "ksbkbht", "kyunki 2"],
  },
  {
    "name": "Kyunki Rishton Ke Bhi Roop Badalte Hai",
    "slug": "kyunki-rishton",
    "aliases": ["kyunki rishton", "krkrb"],
  },
  {
    "name": "Mannat",
    "slug": "mannat",
    "aliases": [],
  },
  {
    "name": "Mangal Lakshmi",
    "slug": "mangal-lakshmi",
    "aliases": ["mangal", "lakshmi"],
  },
  {
    "name": "Mahadev And Sons",
    "slug": "mahadev-and-sons",
    "aliases": ["mahadev", "mahadev sons"],
  },
  {
    "name": "Dr. Aarambhi",
    "slug": "dr-aarambhi",
    "aliases": ["aarambhi", "dr aarambhi"],
  },
  {
    "name": "Do Duniya Ek Dil",
    "slug": "do-duniya-ek-dil",
    "aliases": ["do duniya", "dde"],
  },
  {
    "name": "Bareilly Ke Bachchan",
    "slug": "bareilly-ke-bachchan",
    "aliases": ["bareilly", "bachchan"],
  },
  {
    "name": "Naagin 7",
    "slug": "naagin-7",
    "aliases": ["naagin", "nagin"],
  },
  {
    "name": "Laughter Chef 3",
    "slug": "laughter-chef-3",
    "aliases": ["laughter chef", "laughter", "laughter chef 3", "laughter challenge 3", "laughter challenge", "lc3"],
  },
  {
    "name": "Vasudha",
    "slug": "vasudha",
    "aliases": [],
  },
  {
    "name": "Jagadhatri",
    "slug": "jagadhatri",
    "aliases": ["jagadatri", "jag"],
  },
  {
    "name": "Saru",
    "slug": "saru",
    "aliases": [],
  },
  {
    "name": "Lakshmi Niwas",
    "slug": "lakshmi-niwas",
    "aliases": ["lakshmi niwas"],
  },
  {
    "name": "Tum Se Tum Tak",
    "slug": "tum-se-tum-tak",
    "aliases": ["tum se tum", "tstk"],
  },
  {
    "name": "Ganga Mayi Ki Betiyan",
    "slug": "ganga-mayi",
    "aliases": ["ganga mayi", "ganga"],
  },
  {
    "name": "Jaane Anjaane Hum Mile",
    "slug": "jaane-anjaane",
    "aliases": ["jaane anjaane", "jahm"],
  },
  {
    "name": "Indian Idol 16",
    "slug": "indian-idol-16",
    "aliases": ["indian idol", "idol 16"],
  },
  {
    "name": "India's Best Dancer 5",
    "slug": "indias-best-dancer-5",
    "aliases": ["best dancer", "ibd", "ibd5"],
  },
  {
    "name": "Tum Ho Naa",
    "slug": "tum-ho-naa",
    "aliases": ["tum ho na"],
  },
  {
    "name": "Pushpa Impossible",
    "slug": "pushpa-impossible",
    "aliases": ["pushpa"],
  },
  {
    "name": "Hastinapur Ke Veer",
    "slug": "hastinapur-ke-veer",
    "aliases": ["hastinapur", "hkv"],
  },
  {
    "name": "Taarak Mehta Ka Ooltah Chashmah",
    "slug": "tmkoc",
    "aliases": ["tmkoc", "taarak mehta", "tarak mehta", "tmk"],
  },
  {
    "name": "Hui Gumm Yaadein",
    "slug": "hui-gumm-yaadein",
    "aliases": ["hui gumm", "gumm yaadein"],
  },
]


async def seed_serials(database) -> int:
    count = 0
    for serial in SERIALS:
        result = await database.serials.update_one(
            {"slug": serial["slug"]},
            {
                "$setOnInsert": {
                    "name": serial["name"],
                    "slug": serial["slug"],
                    "aliases": serial["aliases"],
                    "active": True,
                }
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            count += 1
    return count


async def refresh_serial_catalog(database) -> None:
    for serial in SERIALS:
        await database.serials.update_one(
            {"slug": serial["slug"], "deleted_by_admin": {"$ne": True}},
            {
                "$set": {
                    "name": serial["name"],
                    "aliases": serial["aliases"],
                    "active": True,
                },
                "$setOnInsert": {
                    "slug": serial["slug"],
                    "deleted_by_admin": False,
                },
            },
            upsert=True,
        )
