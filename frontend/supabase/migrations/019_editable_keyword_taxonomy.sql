-- Store admin-editable niche keyword taxonomy.

ALTER TABLE system_settings
    ADD COLUMN IF NOT EXISTS keyword_taxonomy jsonb NOT NULL DEFAULT
    '[
        {
                "niche": "gold_investment",
                "keywords": [
                        "physical gold",
                        "gold ira",
                        "precious metals",
                        "bullion",
                        "silver coins",
                        "gold coins",
                        "gold protects",
                        "gold investment"
                ]
        },
        {
                "niche": "retirement",
                "keywords": [
                        "retirement planning",
                        "social security",
                        "fixed income",
                        "401k",
                        "ira rollover",
                        "retirement savings",
                        "pension"
                ]
        },
        {
                "niche": "alternative_media_politics",
                "keywords": [
                        "independent journalism",
                        "free speech",
                        "censorship",
                        "constitutional rights",
                        "alternative media"
                ]
        },
        {
                "niche": "preparedness_self_reliance",
                "keywords": [
                        "emergency preparedness",
                        "food storage",
                        "self reliance",
                        "survival",
                        "prepper",
                        "water storage"
                ]
        },
        {
                "niche": "conservative_politics_commentary",
                "keywords": [
                        "america first",
                        "small government",
                        "limited government",
                        "constitutional republic",
                        "states rights",
                        "election integrity",
                        "voter fraud",
                        "ballot harvesting",
                        "border crisis",
                        "illegal immigration",
                        "mainstream media bias",
                        "free speech absolutist",
                        "woke agenda",
                        "parental rights",
                        "fiscal conservatism",
                        "judicial activism"
                ]
        },
        {
                "niche": "anti_establishment_independent_news",
                "keywords": [
                        "independent journalism",
                        "citizen journalism",
                        "watchdog reporting",
                        "accountability reporting",
                        "media blackout",
                        "narrative control",
                        "corporate media",
                        "legacy media",
                        "censorship",
                        "deplatforming",
                        "whistleblower",
                        "foia request",
                        "follow the money",
                        "manufactured consent",
                        "regulatory capture"
                ]
        },
        {
                "niche": "investigative_journalism",
                "keywords": [
                        "investigative report",
                        "document leak",
                        "public records",
                        "foia documents",
                        "source verification",
                        "offshore accounts",
                        "shell companies",
                        "conflict of interest",
                        "procurement fraud",
                        "bid rigging",
                        "kickback scheme",
                        "audit trail",
                        "ethics violation",
                        "watchdog investigation",
                        "accountability journalism"
                ]
        },
        {
                "niche": "conspiracy_deep_state_truth_seeker",
                "keywords": [
                        "deep state",
                        "false flag",
                        "new world order",
                        "globalist agenda",
                        "shadow government",
                        "cover up",
                        "intel operation",
                        "black budget",
                        "psyop",
                        "mass surveillance state",
                        "elite cabal",
                        "manufactured crisis",
                        "controlled opposition",
                        "red pill",
                        "truth seeker"
                ]
        },
        {
                "niche": "faith_based_biblical_prophecy",
                "keywords": [
                        "bible prophecy",
                        "end times",
                        "second coming",
                        "tribulation",
                        "great tribulation",
                        "rapture",
                        "antichrist",
                        "mark of the beast",
                        "book of revelation",
                        "millennial kingdom",
                        "spiritual warfare",
                        "gospel truth",
                        "biblical worldview",
                        "signs of the times",
                        "kingdom of god"
                ]
        },
        {
                "niche": "prepper_survival_homesteading",
                "keywords": [
                        "emergency preparedness",
                        "disaster supplies kit",
                        "go bag",
                        "72 hour kit",
                        "shelter in place",
                        "off grid",
                        "grid down",
                        "water filtration",
                        "water storage",
                        "long shelf life food",
                        "backup power",
                        "portable generator",
                        "first aid kit",
                        "homesteading",
                        "self reliance"
                ]
        },
        {
                "niche": "finance_economics_crypto",
                "keywords": [
                        "sound money",
                        "fiat currency",
                        "currency debasement",
                        "inflation hedge",
                        "federal funds rate",
                        "monetary policy",
                        "money supply",
                        "de-dollarization",
                        "national debt",
                        "banking crisis",
                        "market crash",
                        "bitcoin",
                        "self custody",
                        "cold wallet",
                        "stablecoin",
                        "on chain"
                ]
        },
        {
                "niche": "health_freedom_alternative_medicine",
                "keywords": [
                        "medical freedom",
                        "informed consent",
                        "natural health",
                        "holistic health",
                        "functional medicine",
                        "integrative medicine",
                        "detox protocol",
                        "immune support",
                        "metabolic health",
                        "gut health",
                        "hormone balance",
                        "non toxic living",
                        "vaccine injury",
                        "health sovereignty",
                        "root cause medicine"
                ]
        },
        {
                "niche": "ufos_aliens_exopolitics",
                "keywords": [
                        "uap",
                        "unidentified anomalous phenomena",
                        "unidentified aerial phenomena",
                        "aaro",
                        "ufo disclosure",
                        "non human intelligence",
                        "crash retrieval",
                        "reverse engineering",
                        "whistleblower testimony",
                        "tic tac uap",
                        "navy encounters",
                        "abduction",
                        "contactee",
                        "exopolitics",
                        "alien technology"
                ]
        },
        {
                "niche": "military_veteran_national_security",
                "keywords": [
                        "national security",
                        "threat assessment",
                        "critical infrastructure",
                        "service connected disability",
                        "va disability claim",
                        "ptsd claim",
                        "va compensation",
                        "veteran benefits",
                        "special operations",
                        "rules of engagement",
                        "force readiness",
                        "intelligence assessment",
                        "border security",
                        "counterterrorism",
                        "transnational threat"
                ]
        },
        {
                "niche": "culture_war_social_commentary",
                "keywords": [
                        "culture war",
                        "cancel culture",
                        "critical race theory",
                        "gender ideology",
                        "identity politics",
                        "woke",
                        "anti woke",
                        "parental rights",
                        "free speech on campus",
                        "dei",
                        "intersectionality",
                        "social engineering",
                        "traditional values",
                        "family values",
                        "moral decline"
                ]
        },
        {
                "niche": "second_amendment_gun_rights",
                "keywords": [
                        "second amendment",
                        "gun rights",
                        "right to bear arms",
                        "constitutional carry",
                        "shall issue",
                        "open carry",
                        "concealed carry",
                        "magazine ban",
                        "assault weapons ban",
                        "red flag laws",
                        "self defense",
                        "stand your ground",
                        "firearms training",
                        "home defense",
                        "gun control"
                ]
        },
        {
                "niche": "tech_privacy_anti_surveillance",
                "keywords": [
                        "digital privacy",
                        "government surveillance",
                        "mass surveillance",
                        "end to end encryption",
                        "metadata",
                        "zero trust",
                        "multi factor authentication",
                        "phishing resistant mfa",
                        "ransomware",
                        "phishing",
                        "zero day",
                        "vpn",
                        "secure messaging",
                        "data broker",
                        "facial recognition"
                ]
        },
        {
                "niche": "legal_constitutional_rights",
                "keywords": [
                        "first amendment",
                        "fourth amendment",
                        "due process",
                        "equal protection",
                        "unreasonable search and seizure",
                        "search warrant",
                        "probable cause",
                        "exclusionary rule",
                        "civil liberties",
                        "constitutional rights",
                        "judicial review",
                        "administrative overreach",
                        "qualified immunity",
                        "habeas corpus",
                        "bill of rights"
                ]
        },
        {
                "niche": "satire_comedy",
                "keywords": [
                        "political satire",
                        "parody",
                        "spoof",
                        "sarcasm",
                        "irony",
                        "comedy sketch",
                        "stand up comedy",
                        "satirical monologue",
                        "roast",
                        "deadpan",
                        "dark humor",
                        "punchline",
                        "clown world",
                        "meme humor",
                        "comedic commentary"
                ]
        },
        {
                "niche": "law_enforcement_crime",
                "keywords": [
                        "organized crime",
                        "human trafficking",
                        "drug trafficking",
                        "money laundering",
                        "identity theft",
                        "wire fraud",
                        "real estate fraud",
                        "asset forfeiture",
                        "gang violence",
                        "cartel activity",
                        "violent crime",
                        "public safety",
                        "cold case",
                        "sex trafficking",
                        "financial crimes"
                ]
        },
        {
                "niche": "alternative_history_archaeology",
                "keywords": [
                        "ancient civilizations",
                        "lost civilization",
                        "forbidden archaeology",
                        "megalithic structures",
                        "ancient cataclysm",
                        "younger dryas",
                        "atlantis theory",
                        "gobekli tepe",
                        "pyramid alignment",
                        "ancient artifacts",
                        "suppressed history",
                        "out of place artifact",
                        "prehistoric advanced culture",
                        "biblical archaeology",
                        "historical revisionism"
                ]
        },
        {
                "niche": "spirituality_metaphysical",
                "keywords": [
                        "higher consciousness",
                        "spiritual awakening",
                        "chakra",
                        "energy healing",
                        "aura",
                        "manifestation",
                        "law of attraction",
                        "astrology",
                        "numerology",
                        "tarot",
                        "divination",
                        "synchronicity",
                        "ascension",
                        "shadow work",
                        "third eye"
                ]
        },
        {
                "niche": "lds_mormon_community",
                "keywords": [
                        "book of mormon",
                        "doctrine and covenants",
                        "pearl of great price",
                        "ward",
                        "stake",
                        "relief society",
                        "elders quorum",
                        "bishop",
                        "temple recommend",
                        "patriarchal blessing",
                        "familysearch",
                        "temple ordinances",
                        "genealogy work",
                        "general conference",
                        "restoration"
                ]
        },
        {
                "niche": "lifestyle_family_travel",
                "keywords": [
                        "family life",
                        "homeschool family",
                        "parenting tips",
                        "marriage advice",
                        "faith and family",
                        "road trip",
                        "rv living",
                        "travel vlog",
                        "expat life",
                        "budget travel",
                        "family preparedness",
                        "remote lifestyle",
                        "digital nomad",
                        "simple living",
                        "work life balance"
                ]
        },
        {
                "niche": "other_unclassified",
                "keywords": [
                        "uncategorized",
                        "misc commentary",
                        "variety channel",
                        "general discussion",
                        "open topic",
                        "mixed content"
                ]
        }
]'::jsonb;

UPDATE system_settings
SET keyword_taxonomy =
    '[
        {
                "niche": "gold_investment",
                "keywords": [
                        "physical gold",
                        "gold ira",
                        "precious metals",
                        "bullion",
                        "silver coins",
                        "gold coins",
                        "gold protects",
                        "gold investment"
                ]
        },
        {
                "niche": "retirement",
                "keywords": [
                        "retirement planning",
                        "social security",
                        "fixed income",
                        "401k",
                        "ira rollover",
                        "retirement savings",
                        "pension"
                ]
        },
        {
                "niche": "alternative_media_politics",
                "keywords": [
                        "independent journalism",
                        "free speech",
                        "censorship",
                        "constitutional rights",
                        "alternative media"
                ]
        },
        {
                "niche": "preparedness_self_reliance",
                "keywords": [
                        "emergency preparedness",
                        "food storage",
                        "self reliance",
                        "survival",
                        "prepper",
                        "water storage"
                ]
        },
        {
                "niche": "conservative_politics_commentary",
                "keywords": [
                        "america first",
                        "small government",
                        "limited government",
                        "constitutional republic",
                        "states rights",
                        "election integrity",
                        "voter fraud",
                        "ballot harvesting",
                        "border crisis",
                        "illegal immigration",
                        "mainstream media bias",
                        "free speech absolutist",
                        "woke agenda",
                        "parental rights",
                        "fiscal conservatism",
                        "judicial activism"
                ]
        },
        {
                "niche": "anti_establishment_independent_news",
                "keywords": [
                        "independent journalism",
                        "citizen journalism",
                        "watchdog reporting",
                        "accountability reporting",
                        "media blackout",
                        "narrative control",
                        "corporate media",
                        "legacy media",
                        "censorship",
                        "deplatforming",
                        "whistleblower",
                        "foia request",
                        "follow the money",
                        "manufactured consent",
                        "regulatory capture"
                ]
        },
        {
                "niche": "investigative_journalism",
                "keywords": [
                        "investigative report",
                        "document leak",
                        "public records",
                        "foia documents",
                        "source verification",
                        "offshore accounts",
                        "shell companies",
                        "conflict of interest",
                        "procurement fraud",
                        "bid rigging",
                        "kickback scheme",
                        "audit trail",
                        "ethics violation",
                        "watchdog investigation",
                        "accountability journalism"
                ]
        },
        {
                "niche": "conspiracy_deep_state_truth_seeker",
                "keywords": [
                        "deep state",
                        "false flag",
                        "new world order",
                        "globalist agenda",
                        "shadow government",
                        "cover up",
                        "intel operation",
                        "black budget",
                        "psyop",
                        "mass surveillance state",
                        "elite cabal",
                        "manufactured crisis",
                        "controlled opposition",
                        "red pill",
                        "truth seeker"
                ]
        },
        {
                "niche": "faith_based_biblical_prophecy",
                "keywords": [
                        "bible prophecy",
                        "end times",
                        "second coming",
                        "tribulation",
                        "great tribulation",
                        "rapture",
                        "antichrist",
                        "mark of the beast",
                        "book of revelation",
                        "millennial kingdom",
                        "spiritual warfare",
                        "gospel truth",
                        "biblical worldview",
                        "signs of the times",
                        "kingdom of god"
                ]
        },
        {
                "niche": "prepper_survival_homesteading",
                "keywords": [
                        "emergency preparedness",
                        "disaster supplies kit",
                        "go bag",
                        "72 hour kit",
                        "shelter in place",
                        "off grid",
                        "grid down",
                        "water filtration",
                        "water storage",
                        "long shelf life food",
                        "backup power",
                        "portable generator",
                        "first aid kit",
                        "homesteading",
                        "self reliance"
                ]
        },
        {
                "niche": "finance_economics_crypto",
                "keywords": [
                        "sound money",
                        "fiat currency",
                        "currency debasement",
                        "inflation hedge",
                        "federal funds rate",
                        "monetary policy",
                        "money supply",
                        "de-dollarization",
                        "national debt",
                        "banking crisis",
                        "market crash",
                        "bitcoin",
                        "self custody",
                        "cold wallet",
                        "stablecoin",
                        "on chain"
                ]
        },
        {
                "niche": "health_freedom_alternative_medicine",
                "keywords": [
                        "medical freedom",
                        "informed consent",
                        "natural health",
                        "holistic health",
                        "functional medicine",
                        "integrative medicine",
                        "detox protocol",
                        "immune support",
                        "metabolic health",
                        "gut health",
                        "hormone balance",
                        "non toxic living",
                        "vaccine injury",
                        "health sovereignty",
                        "root cause medicine"
                ]
        },
        {
                "niche": "ufos_aliens_exopolitics",
                "keywords": [
                        "uap",
                        "unidentified anomalous phenomena",
                        "unidentified aerial phenomena",
                        "aaro",
                        "ufo disclosure",
                        "non human intelligence",
                        "crash retrieval",
                        "reverse engineering",
                        "whistleblower testimony",
                        "tic tac uap",
                        "navy encounters",
                        "abduction",
                        "contactee",
                        "exopolitics",
                        "alien technology"
                ]
        },
        {
                "niche": "military_veteran_national_security",
                "keywords": [
                        "national security",
                        "threat assessment",
                        "critical infrastructure",
                        "service connected disability",
                        "va disability claim",
                        "ptsd claim",
                        "va compensation",
                        "veteran benefits",
                        "special operations",
                        "rules of engagement",
                        "force readiness",
                        "intelligence assessment",
                        "border security",
                        "counterterrorism",
                        "transnational threat"
                ]
        },
        {
                "niche": "culture_war_social_commentary",
                "keywords": [
                        "culture war",
                        "cancel culture",
                        "critical race theory",
                        "gender ideology",
                        "identity politics",
                        "woke",
                        "anti woke",
                        "parental rights",
                        "free speech on campus",
                        "dei",
                        "intersectionality",
                        "social engineering",
                        "traditional values",
                        "family values",
                        "moral decline"
                ]
        },
        {
                "niche": "second_amendment_gun_rights",
                "keywords": [
                        "second amendment",
                        "gun rights",
                        "right to bear arms",
                        "constitutional carry",
                        "shall issue",
                        "open carry",
                        "concealed carry",
                        "magazine ban",
                        "assault weapons ban",
                        "red flag laws",
                        "self defense",
                        "stand your ground",
                        "firearms training",
                        "home defense",
                        "gun control"
                ]
        },
        {
                "niche": "tech_privacy_anti_surveillance",
                "keywords": [
                        "digital privacy",
                        "government surveillance",
                        "mass surveillance",
                        "end to end encryption",
                        "metadata",
                        "zero trust",
                        "multi factor authentication",
                        "phishing resistant mfa",
                        "ransomware",
                        "phishing",
                        "zero day",
                        "vpn",
                        "secure messaging",
                        "data broker",
                        "facial recognition"
                ]
        },
        {
                "niche": "legal_constitutional_rights",
                "keywords": [
                        "first amendment",
                        "fourth amendment",
                        "due process",
                        "equal protection",
                        "unreasonable search and seizure",
                        "search warrant",
                        "probable cause",
                        "exclusionary rule",
                        "civil liberties",
                        "constitutional rights",
                        "judicial review",
                        "administrative overreach",
                        "qualified immunity",
                        "habeas corpus",
                        "bill of rights"
                ]
        },
        {
                "niche": "satire_comedy",
                "keywords": [
                        "political satire",
                        "parody",
                        "spoof",
                        "sarcasm",
                        "irony",
                        "comedy sketch",
                        "stand up comedy",
                        "satirical monologue",
                        "roast",
                        "deadpan",
                        "dark humor",
                        "punchline",
                        "clown world",
                        "meme humor",
                        "comedic commentary"
                ]
        },
        {
                "niche": "law_enforcement_crime",
                "keywords": [
                        "organized crime",
                        "human trafficking",
                        "drug trafficking",
                        "money laundering",
                        "identity theft",
                        "wire fraud",
                        "real estate fraud",
                        "asset forfeiture",
                        "gang violence",
                        "cartel activity",
                        "violent crime",
                        "public safety",
                        "cold case",
                        "sex trafficking",
                        "financial crimes"
                ]
        },
        {
                "niche": "alternative_history_archaeology",
                "keywords": [
                        "ancient civilizations",
                        "lost civilization",
                        "forbidden archaeology",
                        "megalithic structures",
                        "ancient cataclysm",
                        "younger dryas",
                        "atlantis theory",
                        "gobekli tepe",
                        "pyramid alignment",
                        "ancient artifacts",
                        "suppressed history",
                        "out of place artifact",
                        "prehistoric advanced culture",
                        "biblical archaeology",
                        "historical revisionism"
                ]
        },
        {
                "niche": "spirituality_metaphysical",
                "keywords": [
                        "higher consciousness",
                        "spiritual awakening",
                        "chakra",
                        "energy healing",
                        "aura",
                        "manifestation",
                        "law of attraction",
                        "astrology",
                        "numerology",
                        "tarot",
                        "divination",
                        "synchronicity",
                        "ascension",
                        "shadow work",
                        "third eye"
                ]
        },
        {
                "niche": "lds_mormon_community",
                "keywords": [
                        "book of mormon",
                        "doctrine and covenants",
                        "pearl of great price",
                        "ward",
                        "stake",
                        "relief society",
                        "elders quorum",
                        "bishop",
                        "temple recommend",
                        "patriarchal blessing",
                        "familysearch",
                        "temple ordinances",
                        "genealogy work",
                        "general conference",
                        "restoration"
                ]
        },
        {
                "niche": "lifestyle_family_travel",
                "keywords": [
                        "family life",
                        "homeschool family",
                        "parenting tips",
                        "marriage advice",
                        "faith and family",
                        "road trip",
                        "rv living",
                        "travel vlog",
                        "expat life",
                        "budget travel",
                        "family preparedness",
                        "remote lifestyle",
                        "digital nomad",
                        "simple living",
                        "work life balance"
                ]
        },
        {
                "niche": "other_unclassified",
                "keywords": [
                        "uncategorized",
                        "misc commentary",
                        "variety channel",
                        "general discussion",
                        "open topic",
                        "mixed content"
                ]
        }
]'::jsonb
WHERE keyword_taxonomy IS NULL OR keyword_taxonomy = '[]'::jsonb;
