#!/usr/bin/env python3
"""Research every seeded DOAJ journal and export migration-ready metadata.

Each official journal URL is requested and its observable page metadata is
stored as evidence.  Structured bibliographic facts (OA start year, publisher
country, subjects and keywords) come from the matching DOAJ journal record.
Academic programs are selected only from the UFPS seed catalogue using those
subjects, keywords and the official page text.
"""

import argparse
import gzip
import html
import ipaddress
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import requests


USER_AGENT = "RABD-JournalResearch/1.0 (+academic migration enrichment)"
DOAJ_SEARCH_URL = "https://doaj.org/api/search/journals/"
MAX_PAGE_BYTES = 1_500_000

# Ordered from specific to broad. At most three matching programs are kept.
PROGRAM_RULES = (
    ("tecnología en analítica de datos", r"data (science|analytics|mining)|big data|machine learning|estad.stic|estat.stic|inteligencia artificial"),
    ("ingeniería de sistemas", r"computer|computing|software|informatics|information system|sistema(s)? de informaci.n|computaci.n|inform.tica|cyber"),
    ("ingeniería electrónica", r"electronic|telecommunication|signal processing|circuit|semiconductor|roboti|control autom"),
    ("ingeniería electromecánica", r"electromechan|electrical engineering|power system|energ.a el.ctrica"),
    ("ingeniería mecánica", r"mechanic|thermodynamic|fluid mechanics|m.quinas|automotive|manufacturing engineering"),
    ("ingeniería civil", r"civil engineering|construction|concrete|structur(al|e)|geotechn|pavement|hormig.n"),
    ("tecnología en obras civiles", r"public works|obra(s)? civil|building construction"),
    ("arquitectura", r"architectur|urbanis|urban planning|built environment|dise.o urbano"),
    ("ingeniería de minas", r"mining|mine safety|mineral|geolog|petroleum|reservoir|miner.a"),
    ("maestría en ingeniería de recursos hidráulicos", r"hydraulic|hydrolog|water resource|watershed|recursos h.dricos|cuenca"),
    ("ingeniería ambiental", r"environment|ecolog|climate|sustainab|pollution|waste|biodivers|medio ambient|ambiental"),
    ("ingeniería agronómica", r"agronom|crop|soil science|plant science|agricultur|agroecolog|cultivo|suelo"),
    ("zootecnia", r"animal science|livestock|veterinar|poultry|cattle|aquaculture|zootec|ganader"),
    ("ingeniería agroindustrial", r"food science|food technolog|food processing|agroindustr|alimento|postharvest"),
    ("ingeniería biotecnológica", r"biotechn|genetic|genomic|microbiolog|molecular biolog|bioinform|biotecn"),
    ("maestría en ciencias biológicas", r"biology|biological|botan|zoolog|life science|neuroscience|biolog.a"),
    ("química industrial", r"chemistry|chemical|polymer|cataly|material science|qu.mic|nanomaterial"),
    ("tecnología en regencia de farmacia", r"pharmac|drug|toxicolog|medicinal chemistry|farmac|therapeut"),
    ("enfermería", r"nurs|clinical|medicine|medical|public health|patient|salud|epidemiol|disease|surgery"),
    ("seguridad y salud en el trabajo", r"occupational health|workplace safety|industrial hygiene|salud ocupacional|seguridad laboral"),
    ("licenciatura en matemáticas", r"mathemat|algebra|geometry|topology|number theory|matem.t"),
    ("maestría en educación matemática", r"mathematics education|ense.anza de las matem|educa..o matem"),
    ("licenciatura en ciencias naturales y educación ambiental", r"science education|natural science|physics|astronom|optics|f.sica|ense.anza de las ciencias"),
    ("licenciatura en educación infantil", r"early childhood|preschool|child education|educaci.n infantil|inf.ncia"),
    ("maestría en práctica pedagógica", r"pedagog|teaching|teacher education|didactic|curricul|educaci.n|education"),
    ("comunicación social", r"journalis|communication|media studies|film|television|radio|semiotic|comunicaci.n|periodis"),
    ("derecho", r"\blaw\b|legal|jurisprud|crimin|derecho|jur.dic|legislat"),
    ("maestría en derecho público: gobierno, justicia y derechos humanos", r"human rights|constitutional|public law|government|derechos humanos|derecho p.blico"),
    ("trabajo social", r"social work|social welfare|community|inequal|social policy|sociolog|trabajo social"),
    ("maestría en estudios sociales y educación para la paz", r"peace|conflict|history|anthropolog|political science|social science|paz|conflicto|historia"),
    ("administración de empresas", r"business|management|organization|entrepreneur|marketing|administraci.n|gerencia"),
    ("administración financiera", r"finance|financial|banking|investment|finanzas|mercado de capital"),
    ("contaduría pública", r"accounting|audit|taxation|contabilidad|auditor.a|tribut"),
    ("comercio internacional", r"international trade|foreign trade|global trade|comercio exterior|comercio internacional"),
    ("maestría en negocios internacionales", r"international business|global business|negocios internacionales"),
    ("ingeniería industrial", r"industrial engineering|operations research|production|quality management|supply chain|logistic|ingenier.a industrial"),
    ("licenciatura en educación comunitaria", r"philosoph|psycholog|religion|ethic|cultural studies|filosof|psicolog|teolog"),
)

SUBJECT_FALLBACKS = (
    (r"language|literature|philolog", "comunicación social"),
    (r"education", "maestría en práctica pedagógica"),
    (r"medicine|health", "enfermería"),
    (r"science", "licenciatura en ciencias naturales y educación ambiental"),
    (r"technology|engineering", "ingeniería industrial"),
    (r"agricultur", "ingeniería agronómica"),
    (r"business|econom", "administración de empresas"),
    (r"social science|history|geograph|anthropolog", "maestría en estudios sociales y educación para la paz"),
    (r"law|political", "derecho"),
    (r"art|music", "comunicación social"),
    (r"general works|bibliograph|library", "comunicación social"),
)

# LCC subject terms are the primary classification evidence. This avoids false
# positives such as assigning Business Administration to a medical journal
# merely because one keyword says "pain management".
SUBJECT_PROGRAM_RULES = (
    (r"pharmacy|pharmacology|therapeutics|pharmaceutical|toxicology", "tecnología en regencia de farmacia"),
    (r"medicine|medical|nursing|surgery|disease|pediatrics|dermatology|dentistry|health|neurology|psychiatry|oncology|anesthesiology|ophthalmology|physiology", "enfermería"),
    (r"industrial medicine|industrial hygiene|sports medicine", "seguridad y salud en el trabajo"),
    (r"biotechnology|genetics|microbiology|biochemistry|molecular", "ingeniería biotecnológica"),
    (r"biology|botany|zoology|natural history|neuroscience", "maestría en ciencias biológicas"),
    (r"veterinary|animal culture|animal science|aquaculture|fisheries", "zootecnia"),
    (r"food processing|nutrition|food supply", "ingeniería agroindustrial"),
    (r"agriculture|plant culture|forestry|soil", "ingeniería agronómica"),
    (r"environment|ecology|oceanography|meteorology|climatology|renewable energy|human ecology", "ingeniería ambiental"),
    (r"mining|mineralogy|geology|metallurgy", "ingeniería de minas"),
    (r"hydraulic|water supply|hydrology", "maestría en ingeniería de recursos hidráulicos"),
    (r"civil engineering|building construction|structural engineering|geodesy|engineering geology", "ingeniería civil"),
    (r"architecture|building design|urban renewal|urban redevelopment", "arquitectura"),
    (r"mechanical engineering|machinery|applied mechanics|motor vehicles", "ingeniería mecánica"),
    (r"electrical engineering|electronics|electric apparatus|electric energy|nuclear engineering|photonics|optics|atomic power", "ingeniería electrónica"),
    (r"computer|information technology|cybernetics|information theory|software|systems engineering|natural language processing", "ingeniería de sistemas"),
    (r"statistics|data mining|quantitative methods|mathematical statistics", "tecnología en analítica de datos"),
    (r"mathematics|algebra|geometry|analysis$", "licenciatura en matemáticas"),
    (r"chemistry|chemical|polymers|oils, fats", "química industrial"),
    (r"early childhood|preschool", "licenciatura en educación infantil"),
    (r"mathematics education", "maestría en educación matemática"),
    (r"science education", "licenciatura en ciencias naturales y educación ambiental"),
    (r"education|teaching|learning|vocational guidance", "maestría en práctica pedagógica"),
    (r"accounting|bookkeeping|audit", "contaduría pública"),
    (r"finance|banking|investment", "administración financiera"),
    (r"international trade|commerce|commercial", "comercio internacional"),
    (r"business|management|marketing|industrial productivity|personnel management|real estate", "administración de empresas"),
    (r"public law|constitutional|human rights|public administration", "maestría en derecho público: gobierno, justicia y derechos humanos"),
    (r"law|jurisprudence|legal|criminology", "derecho"),
    (r"social welfare|social pathology|family|marriage|communities|classes|races", "trabajo social"),
    (r"political science|international relations|social science|sociology|anthropology|archaeology|history|geography|military science|naval science|civilization|women|feminism", "maestría en estudios sociales y educación para la paz"),
    (r"communication|mass media|journalism|motion pictures", "comunicación social"),
    (r"language|literature|philology|linguistic|arts|music|museums|bibliography|library|archives|periodicals", "comunicación social"),
    (r"philosophy|psychology|religion|theology|ethics|islam|christianity|bible|mythology", "licenciatura en educación comunitaria"),
    (r"physics|astronomy|science", "licenciatura en ciencias naturales y educación ambiental"),
    (r"technology|engineering|production management", "ingeniería industrial"),
    (r"sports|recreation", "seguridad y salud en el trabajo"),
    (r"general works", "comunicación social"),
)

COUNTRY_BY_TLD = {
    "au": "AU", "br": "BR", "ca": "CA", "ch": "CH", "cl": "CL",
    "cn": "CN", "co": "CO", "cz": "CZ", "de": "DE", "dk": "DK",
    "ec": "EC", "es": "ES", "fi": "FI", "fr": "FR", "gr": "GR",
    "hr": "HR", "hu": "HU", "id": "ID", "in": "IN", "ir": "IR",
    "it": "IT", "jp": "JP", "kr": "KR", "lt": "LT", "lv": "LV",
    "mx": "MX", "my": "MY", "ng": "NG", "nl": "NL", "no": "NO",
    "nz": "NZ", "pe": "PE", "ph": "PH", "pk": "PK", "pl": "PL",
    "pt": "PT", "ro": "RO", "rs": "RS", "ru": "RU", "se": "SE",
    "si": "SI", "sk": "SK", "th": "TH", "tr": "TR", "tw": "TW",
    "ua": "UA", "uk": "GB", "us": "US", "uy": "UY", "ve": "VE",
    "vn": "VN", "za": "ZA",
}


def _normalized(value):
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in value if not unicodedata.combining(char)).lower()


def _clean_markup(value):
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _meta(content, name):
    patterns = (
        rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']',
        rf'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\']{re.escape(name)}["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, content, flags=re.I | re.S)
        if match:
            return _clean_markup(match.group(1))[:2000]
    return ""


def _public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        return False
    try:
        return ipaddress.ip_address(hostname).is_global
    except ValueError:
        # The harvested source URLs already passed the backend's DNS-based SSRF
        # validation. Avoid repeating blocking DNS lookups in every worker;
        # redirects are still restricted to HTTP(S) and non-local hostnames.
        return True


def research_page(url):
    checked_at = datetime.now(timezone.utc).isoformat()
    current = url
    try:
        for _ in range(6):
            if not _public_url(current):
                raise ValueError("unsafe or non-public destination")
            response = requests.get(
                current,
                timeout=(8, 20),
                allow_redirects=False,
                stream=True,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            )
            if response.is_redirect or response.is_permanent_redirect:
                target = response.headers.get("location")
                if not target:
                    break
                current = urljoin(current, target)
                continue
            payload = bytearray()
            for chunk in response.iter_content(65536):
                payload.extend(chunk)
                if len(payload) >= MAX_PAGE_BYTES:
                    break
            encoding = response.encoding or "utf-8"
            content = bytes(payload).decode(encoding, errors="replace")
            title_match = re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S)
            title = _clean_markup(title_match.group(1))[:500] if title_match else ""
            description = _meta(content, "description") or _meta(content, "og:description")
            keywords = _meta(content, "keywords")
            return {
                "requested_url": url,
                "final_url": current,
                "http_status": response.status_code,
                "checked_at": checked_at,
                "title": title,
                "description": description,
                "keywords": keywords,
                "error": None,
            }
        raise ValueError("too many redirects")
    except Exception as exc:
        return {
            "requested_url": url,
            "final_url": current,
            "http_status": None,
            "checked_at": checked_at,
            "title": "",
            "description": "",
            "keywords": "",
            "error": f"{type(exc).__name__}: {exc}"[:500],
        }


def load_seed(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        snapshot = json.load(stream)
    latest = {}
    for row in snapshot["journals"]:
        latest[row["issn"].upper()] = row
    return latest


def fetch_doaj_records(issns, batch_size=40):
    records = {}
    for offset in range(0, len(issns), batch_size):
        batch = issns[offset:offset + batch_size]
        query = "issn:(" + " OR ".join(batch) + ")"
        url = DOAJ_SEARCH_URL + quote(query, safe=":()") + f"?pageSize={len(batch) + 10}"
        response = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        payload = response.json()
        for item in payload["results"]:
            bibjson = item.get("bibjson", {})
            identifiers = {bibjson.get("eissn"), bibjson.get("pissn")}
            for identifier in identifiers - {None}:
                records[identifier.upper()] = item
        print(f"doaj={min(offset + len(batch), len(issns))}/{len(issns)}", flush=True)
    return records


def classify_programs(seed_row, bibjson, page):
    subjects = [item.get("term", "") for item in bibjson.get("subject", [])]
    keywords = bibjson.get("keywords", [])
    subject_text = _normalized(" ".join(subjects))
    programs = []
    for pattern, program in SUBJECT_PROGRAM_RULES:
        if re.search(pattern, subject_text, flags=re.I) and program not in programs:
            programs.append(program)
        if len(programs) == 3:
            break
    if programs:
        return programs, subjects, keywords

    evidence_text = " ".join(
        [seed_row["title"], *subjects, *keywords, page["title"], page["description"], page["keywords"]]
    )
    normalized = _normalized(evidence_text)
    for program, pattern in PROGRAM_RULES:
        if re.search(pattern, normalized, flags=re.I):
            programs.append(program)
        if len(programs) == 3:
            break
    if not programs:
        for pattern, program in SUBJECT_FALLBACKS:
            if re.search(pattern, subject_text, flags=re.I):
                programs.append(program)
                break
    if not programs:
        programs.append("comunicación social")
    return programs, subjects, keywords


def country_for(seed_row, bibjson, page):
    publisher_country = (bibjson.get("publisher") or {}).get("country")
    institution_country = (bibjson.get("institution") or {}).get("country")
    if publisher_country:
        return publisher_country.upper(), "doaj.publisher.country"
    if institution_country:
        return institution_country.upper(), "doaj.institution.country"
    host = urlsplit(page["final_url"] or seed_row["url"]).hostname or ""
    tld = host.rsplit(".", 1)[-1].lower()
    if tld in COUNTRY_BY_TLD:
        return COUNTRY_BY_TLD[tld], "official_page.country_tld"
    raise RuntimeError(f"No country evidence for {seed_row['issn']}")


def build_enrichment(seed_rows, doaj_records, pages):
    output = []
    for issn, seed_row in seed_rows.items():
        item = doaj_records.get(issn)
        if item is None:
            raise RuntimeError(f"DOAJ returned no journal record for {issn}")
        bibjson = item["bibjson"]
        page = pages[issn]
        year = bibjson.get("oa_start")
        if not isinstance(year, int) or not 1600 <= year <= datetime.now().year:
            raise RuntimeError(f"Invalid oa_start for {issn}: {year!r}")
        country, country_source = country_for(seed_row, bibjson, page)
        programs, subjects, keywords = classify_programs(seed_row, bibjson, page)
        output.append({
            "issn": issn,
            "title": seed_row["title"],
            "publication_date": f"{year:04d}-01-01",
            "countries": [country],
            "material_types": ["revista"],
            "academic_programs": programs,
            "evidence": {
                "official_page": page,
                "doaj_id": item.get("id"),
                "doaj_last_updated": item.get("last_updated"),
                "oa_start": year,
                "publication_date_source": "doaj.bibjson.oa_start",
                "publisher": bibjson.get("publisher"),
                "institution": bibjson.get("institution"),
                "country_source": country_source,
                "subjects": subjects,
                "keywords": keywords,
                "program_classification_basis": "official page + DOAJ subjects/keywords",
            },
        })
    return sorted(output, key=lambda row: row["issn"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--reuse-link-checks",
        action="store_true",
        help=(
            "Reuse the backend check-links evidence already stored in the "
            "harvest snapshot instead of requesting the pages again."
        ),
    )
    args = parser.parse_args()

    seed_rows = load_seed(args.snapshot)
    issns = sorted(seed_rows)
    doaj_records = fetch_doaj_records(issns)
    missing = sorted(set(issns) - set(doaj_records))
    if missing:
        raise RuntimeError(f"Missing {len(missing)} DOAJ records: {missing[:10]}")

    pages = {}
    if args.reuse_link_checks:
        for issn, row in seed_rows.items():
            pages[issn] = {
                "requested_url": row["url"],
                "final_url": row["url"],
                "http_status": row["url_http_status"],
                "checked_at": row["url_checked_at"],
                "title": "",
                "description": "",
                "keywords": "",
                "error": None if row["url_available"] else "backend check-links failed",
            }
        print(f"pages={len(pages)}/{len(issns)} (backend evidence)", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(research_page, seed_rows[issn]["url"]): issn
                for issn in issns
            }
            for index, future in enumerate(as_completed(futures), start=1):
                issn = futures[future]
                pages[issn] = future.result()
                if index % 25 == 0 or index == len(issns):
                    print(f"pages={index}/{len(issns)}", flush=True)

    enrichment = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "official_pages_requested": len(pages),
            "bibliographic_source": "DOAJ journal Search API by harvested ISSN",
            "publication_date_semantics": "DOAJ open-access start year, January 1",
            "image_assignment": "intentionally omitted",
        },
        "journals": build_enrichment(seed_rows, doaj_records, pages),
    }
    args.output.write_text(
        json.dumps(enrichment, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    ok_pages = sum(row["evidence"]["official_page"]["http_status"] is not None for row in enrichment["journals"])
    print(f"complete={len(enrichment['journals'])} pages_responded={ok_pages} pages_failed={len(issns) - ok_pages}")


if __name__ == "__main__":
    main()
