"""Read public job boards. Each connector returns every listed posting, unfiltered.

Only documented public endpoints are used: no account, cookie or API key.
Detail pages are fetched lazily through ``RawJob.details`` so that only the
postings that pass the title filter cost an extra request.
"""
from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote

import requests

from .config import Source
from .dates import iso_day, workday_posted

TIMEOUT = (8, 25)
HEADERS = {"User-Agent": "EmJobs/1.0 (public job board reader)", "Accept": "application/json"}


@dataclass
class RawJob:
    title: str
    locations: list[str]
    url: str
    published: str = ""
    employment: str = ""
    description: str = ""
    deadline: str = ""
    details: Callable[["RawJob"], None] | None = field(default=None, repr=False)
    company: str = ""  # Job boards listing several employers (JobTeaser) set the employer here.

    def load_details(self) -> None:
        if self.details:
            loader, self.details = self.details, None
            loader(self)


def plain_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _get(session: requests.Session, url: str, **kwargs):
    response = session.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    return response.json()


def greenhouse(source: Source, session: requests.Session) -> list[RawJob]:
    payload = _get(session, f"https://boards-api.greenhouse.io/v1/boards/{source.slug}/jobs",
                   params={"content": "true"})
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("réponse Greenhouse inattendue")
    jobs = []
    for item in payload["jobs"]:
        if not isinstance(item, dict):
            continue
        locations = [str((item.get("location") or {}).get("name") or "")]
        locations += [str(office.get("name") or "") + " " + str(office.get("location") or "")
                      for office in item.get("offices") or [] if isinstance(office, dict)]
        employment = " ".join(str(m.get("value") or "") for m in item.get("metadata") or []
                              if isinstance(m, dict) and isinstance(m.get("value"), str))
        jobs.append(RawJob(
            title=str(item.get("title") or ""), locations=locations,
            url=str(item.get("absolute_url") or ""), published=iso_day(item.get("first_published")),
            employment=employment, description=plain_text(item.get("content") or ""),
            deadline=iso_day(item.get("application_deadline")),
        ))
    return jobs


def lever(source: Source, session: requests.Session) -> list[RawJob]:
    payload = None
    for host in ("api.lever.co", "api.eu.lever.co"):
        try:
            payload = _get(session, f"https://{host}/v0/postings/{source.slug}", params={"mode": "json"})
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                continue
            raise
        if payload:
            break
    if not isinstance(payload, list):
        raise ValueError("tableau Lever introuvable")
    jobs = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        categories = item.get("categories") or {}
        locations = [str(categories.get("location") or "")] + [str(v) for v in categories.get("allLocations") or []]
        jobs.append(RawJob(
            title=str(item.get("text") or ""), locations=locations,
            url=str(item.get("hostedUrl") or ""), published=iso_day(item.get("createdAt")),
            employment=str(categories.get("commitment") or ""),
            description=plain_text(" ".join(str(item.get(k) or "") for k in ("descriptionPlain", "additionalPlain"))
                                   + " " + " ".join(plain_text(str(l.get("content") or ""))
                                                    for l in item.get("lists") or [] if isinstance(l, dict))),
        ))
    return jobs


def ashby(source: Source, session: requests.Session) -> list[RawJob]:
    payload = _get(session, f"https://api.ashbyhq.com/posting-api/job-board/{source.slug}")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("réponse Ashby inattendue")
    jobs = []
    for item in payload["jobs"]:
        if not isinstance(item, dict) or item.get("isListed") is False:
            continue
        address = ((item.get("address") or {}).get("postalAddress") or {})
        locations = [str(item.get("location") or ""), str(address.get("addressLocality") or "")]
        locations += [str(loc.get("location") or "") for loc in item.get("secondaryLocations") or []
                      if isinstance(loc, dict)]
        jobs.append(RawJob(
            title=str(item.get("title") or ""), locations=locations,
            url=str(item.get("jobUrl") or ""), published=iso_day(item.get("publishedAt")),
            employment=str(item.get("employmentType") or ""),
            description=str(item.get("descriptionPlain") or "") or plain_text(item.get("descriptionHtml") or ""),
        ))
    return jobs


def smartrecruiters(source: Source, session: requests.Session) -> list[RawJob]:
    base = f"https://api.smartrecruiters.com/v1/companies/{quote(source.slug)}/postings"
    jobs, offset = [], 0
    while offset < 2000:
        payload = _get(session, base, params={"limit": 100, "offset": offset})
        rows = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("réponse SmartRecruiters inattendue")
        for item in rows:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            location = item.get("location") or {}
            identity = str(item["id"])
            levels = " ".join(str((item.get(k) or {}).get("label") or "") for k in ("typeOfEmployment", "experienceLevel"))

            def details(job: RawJob, identity=identity) -> None:
                data = _get(session, f"{base}/{identity}")
                sections = ((data.get("jobAd") or {}).get("sections") or {}) if isinstance(data, dict) else {}
                job.description = plain_text(" ".join(str((s or {}).get("text") or "") for s in sections.values()))

            jobs.append(RawJob(
                title=str(item.get("name") or ""),
                locations=[" ".join(str(location.get(k) or "") for k in ("city", "region", "country"))],
                url=f"https://jobs.smartrecruiters.com/{source.slug}/{identity}",
                published=iso_day(item.get("releasedDate")), employment=levels, details=details,
            ))
        offset += 100
        if offset >= int(payload.get("totalFound") or 0):
            break
    return jobs


def _patient(send, *args, attempts: int = 4, **kwargs) -> requests.Response:
    """Retry rate limits (429) and transient 5xx with a growing pause."""
    headers = {**HEADERS, **kwargs.pop("headers", {})}
    for attempt in range(attempts):
        response = send(*args, headers=headers, timeout=TIMEOUT, **kwargs)
        if response.status_code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
            response.raise_for_status()
            return response
        retry = response.headers.get("Retry-After", "")
        time.sleep(min(30, int(retry)) if retry.isdigit() else 4 * (attempt + 1))
    raise AssertionError("unreachable")


# Searches sent to platforms that cannot list a whole catalogue cheaply.
SEARCH_TERMS = ("product", "produit", "product owner", "intern", "internship", "stage", "graduate",
                "junior", "strategy", "UX")
# Workday rate-limits shared clusters: fewer searches, at most 5 pages each.
WORKDAY_TERMS = ("product", "produit", "intern", "graduate", "UX", "growth")


def workday(source: Source, session: requests.Session) -> list[RawJob]:
    host, tenant, site = source.slug.split("/")
    api = f"https://{host}/wday/cxs/{tenant}/{site}"
    found: dict[str, RawJob] = {}
    # Keyword searches keep large catalogues (banks, Big Tech) to a few pages;
    # details are read later, only for titles that pass the Em Jobs filter.
    for term in WORKDAY_TERMS:
        for offset in range(0, 100, 20):
            response = _patient(session.post, f"{api}/jobs", headers={"Content-Type": "application/json"},
                                json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term})
            payload = response.json()
            postings = payload.get("jobPostings") if isinstance(payload, dict) else None
            if not isinstance(postings, list):
                raise ValueError("réponse Workday inattendue")
            for item in postings:
                path = str(item.get("externalPath") or "")
                if not path.startswith("/job/") or path in found:
                    continue

                def details(job: RawJob, path=path) -> None:
                    info = (_patient(session.get, f"{api}{path}").json() or {}).get("jobPostingInfo") or {}
                    job.locations = [str(info.get("location") or "")] + [str(l) for l in info.get("additionalLocations") or []]
                    job.description = plain_text(info.get("jobDescription") or "")
                    job.employment = str(info.get("timeType") or "")
                    job.published = iso_day(info.get("startDate")) or job.published

                found[path] = RawJob(
                    title=str(item.get("title") or ""), locations=[str(item.get("locationsText") or "")],
                    url=f"https://{host}/{site}{path}", published=workday_posted(str(item.get("postedOn") or "")),
                    details=details,
                )
            if len(postings) < 20:
                break
            time.sleep(0.5)
        time.sleep(0.5)
    return list(found.values())


def oracle(source: Source, session: requests.Session) -> list[RawJob]:
    """Oracle Recruiting Cloud (Candidate Experience): host/siteNumber, e.g. jpmc.fa.oraclecloud.com/CX_1001."""
    host, site = source.slug.split("/")
    root = f"https://{host}"
    endpoint = f"{root}/hcmRestApi/resources/11.13.18.05/recruitingCEJobRequisitions"
    found: dict[str, RawJob] = {}
    for term in SEARCH_TERMS:
        offset = 0
        while offset < 400:
            payload = _patient(session.get, endpoint, params={
                "onlyData": "true", "expand": "requisitionList.secondaryLocations",
                "finder": f"findReqs;siteNumber={site},keyword=\"{term}\",limit=50,offset={offset}"}).json()
            items = payload.get("items") or []
            meta = items[0] if items and isinstance(items[0], dict) else {}
            rows = meta.get("requisitionList") or []
            for row in rows:
                identity = str(row.get("Id") or "")
                if not identity or identity in found:
                    continue
                locations = [str(row.get("PrimaryLocation") or "")]
                locations += [str(l.get("Name") or "") for l in row.get("secondaryLocations") or [] if isinstance(l, dict)]

                def details(job: RawJob, identity=identity) -> None:
                    data = _patient(session.get, f"{root}/hcmRestApi/resources/11.13.18.05/recruitingCEJobRequisitionDetails",
                                    params={"onlyData": "true", "expand": "all",
                                            "finder": f"ById;Id=\"{identity}\",siteNumber={site}"}).json()
                    info = (data.get("items") or [{}])[0]
                    job.description = plain_text(" ".join(str(info.get(k) or "") for k in (
                        "ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")))
                    job.employment = " ".join(str(info.get(k) or "") for k in ("WorkerType", "JobSchedule", "ContractType"))

                found[identity] = RawJob(
                    title=str(row.get("Title") or ""), locations=locations,
                    url=f"{root}/hcmUI/CandidateExperience/en/sites/{site}/job/{identity}",
                    published=iso_day(row.get("PostedDate")), details=details,
                    description=plain_text(row.get("ShortDescriptionStr") or ""),
                )
            total = int(meta.get("TotalJobsCount") or 0)
            offset += 50
            if not rows or offset >= total:
                break
    return list(found.values())


def successfactors(source: Source, session: requests.Session) -> list[RawJob]:
    """SAP SuccessFactors career sites: host/path, e.g. careers.example.com/search (keyword search pages)."""
    host, _, path = source.slug.partition("/")
    base = f"https://{host}/{path or 'search'}/"
    found: dict[str, RawJob] = {}
    row_pattern = re.compile(r'<tr class="data-row".*?</tr>', re.S | re.I)
    for term in SEARCH_TERMS:
        for start in range(0, 250, 25):
            page = _patient(session.get, base, params={"q": term, "startrow": start},
                            headers={"Accept": "text/html"}).text
            rows = row_pattern.findall(page)
            for row in rows:
                link = re.search(r'href="(/[^"]*?/job/[^"]+?/(\d+)/)"[^>]*>(.*?)</a>', row, re.S)
                if not link or link.group(2) in found:
                    continue
                location = re.search(r'class="jobLocation"[^>]*>(.*?)</span>', row, re.S)
                published = re.search(r'class="jobDate"[^>]*>(.*?)</span>', row, re.S)
                url = f"https://{host}{html.unescape(link.group(1))}"

                def details(job: RawJob, url=url) -> None:
                    text = _patient(session.get, url, headers={"Accept": "text/html"}).text
                    body = re.search(r'<span class="jobdescription">(.*?)</span>\s*</div>', text, re.S)
                    job.description = plain_text(body.group(1) if body else text)[:20000]

                found[link.group(2)] = RawJob(
                    title=plain_text(link.group(3)), locations=[plain_text(location.group(1)) if location else ""],
                    url=url, published=_sf_date(plain_text(published.group(1)) if published else ""), details=details)
            if len(rows) < 25:
                break
    return list(found.values())


def _sf_date(value: str) -> str:
    for fmt in ("%b %d, %Y", "%d %b %Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return time.strftime("%Y-%m-%d", time.strptime(value, fmt))
        except ValueError:
            continue
    return ""


def teamtailor(source: Source, session: requests.Session) -> list[RawJob]:
    """Teamtailor public RSS feed: slug is the career subdomain (slug.teamtailor.com) or a full host."""
    host = source.slug if "." in source.slug else f"{source.slug}.teamtailor.com"
    response = _patient(session.get, f"https://{host}/jobs.rss", headers={"Accept": "application/rss+xml"})
    if "<rss" not in response.text[:1000]:
        raise ValueError("flux RSS Teamtailor introuvable")
    jobs = []
    for item in re.findall(r"<item>(.*?)</item>", response.text, re.S):
        def tag(name: str) -> str:
            match = re.search(rf"<{name}[^>]*>(.*?)</{name}>", item, re.S)
            return plain_text(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(1), flags=re.S)) if match else ""
        locations = [plain_text(m) for m in re.findall(r"<tt:(?:city|name|country)>(.*?)</tt:(?:city|name|country)>", item, re.S)]
        published = ""
        try:
            published = time.strftime("%Y-%m-%d", time.strptime(tag("pubDate")[:16], "%a, %d %b %Y"))
        except ValueError:
            pass
        jobs.append(RawJob(title=tag("title"), locations=[" ".join(locations)] or [""], url=tag("link"),
                           published=published, description=tag("description"),
                           employment=tag("tt:employment-type") or tag("tt:employmentType")))
    return jobs


def workable(source: Source, session: requests.Session) -> list[RawJob]:
    payload = _patient(session.get, f"https://apply.workable.com/api/v1/widget/accounts/{source.slug}",
                       params={"details": "true"}).json()
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("réponse Workable inattendue")
    jobs = []
    for item in payload["jobs"]:
        locations = [" ".join(str(item.get(k) or "") for k in ("city", "state", "country"))]
        locations += [" ".join(str(l.get(k) or "") for k in ("city", "country")) for l in item.get("locations") or []
                      if isinstance(l, dict)]
        jobs.append(RawJob(title=str(item.get("title") or ""), locations=locations,
                           url=str(item.get("url") or item.get("shortlink") or ""),
                           published=iso_day(item.get("published_on") or item.get("created_at")),
                           employment=str(item.get("employment_type") or ""),
                           description=plain_text(item.get("description") or "")))
    return jobs


def recruitee(source: Source, session: requests.Session) -> list[RawJob]:
    payload = _patient(session.get, f"https://{source.slug}.recruitee.com/api/offers/").json()
    if not isinstance(payload, dict) or not isinstance(payload.get("offers"), list):
        raise ValueError("réponse Recruitee inattendue")
    jobs = []
    for item in payload["offers"]:
        locations = [str(item.get("location") or ""), str(item.get("city") or "")]
        locations += [str(l.get("city") or "") for l in item.get("locations") or [] if isinstance(l, dict)]
        jobs.append(RawJob(title=str(item.get("title") or ""), locations=locations,
                           url=str(item.get("careers_url") or ""), published=iso_day(item.get("published_at")),
                           employment=str(item.get("employment_type_code") or ""),
                           description=plain_text(str(item.get("description") or "") + " " + str(item.get("requirements") or ""))))
    return jobs


def _html(session: requests.Session, url: str, **kwargs) -> str:
    return _patient(session.get, url, headers={"Accept": "text/html"}, **kwargs).text


def _fr_day(value: str) -> str:
    """YYYY-MM-DD from "24/11/2026" (day first), "2026/11/24" or ISO text; "" if unreadable."""
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value or "")
    text = f"{match[3]}-{int(match[2]):02d}-{int(match[1]):02d}" if match else str(value or "")[:10].replace("/", "-")
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else ""


def _jsonld_posting(page: str) -> dict:
    for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return {}


def socgen(source: Source, session: requests.Session) -> list[RawJob]:
    """Société Générale careers site: its worldwide (English) and French public offer indexes."""
    found: dict[str, RawJob] = {}
    card = re.compile(r'data-offer-id="([A-Z0-9]+)".*?<a href="(https://[^"]+)"[^>]*>(.*?)</a>(.*?)</div>', re.S)
    for path in ("en/Technical/all-job-offers", "fr/Technical/toutes-les-offres"):
        cards = card.findall(_html(session, f"https://{source.slug}/{path}"))
        if not cards:
            raise ValueError("liste d'offres Société Générale introuvable")
        for identity, url, title, tags in cards:
            if identity in found:
                continue

            def tag(icon: str, tags=tags) -> str:
                match = re.search(rf"fa-{icon}[^>]*></i>(.*?)</span>", tags, re.S)
                return plain_text(match[1]) if match else ""

            def details(job: RawJob) -> None:
                posting = _jsonld_posting(_html(session, job.url))
                job.description = plain_text(posting.get("description") or "")
                # validThrough is not used: this site fills it with the start date, not a closing date.
                job.published = iso_day(_fr_day(str(posting.get("datePosted") or "")))

            found[identity] = RawJob(title=plain_text(title), locations=[tag("location-arrow")], url=url,
                                     employment=tag("copy"), details=details)
    return list(found.values())


def bpce(source: Source, session: requests.Session) -> list[RawJob]:
    """Groupe BPCE open-data export: Natixis, Banques Populaires, Caisses d'Epargne, BRED..."""
    rows = _patient(session.get, f"https://bpce.opendatasoft.com/api/explore/v2.1/catalog/datasets/{source.slug}/exports/json",
                    params={"select": "title,url,city,state,country,jobtype,organization,description"}).json()
    if not isinstance(rows, list):
        raise ValueError("export Open Data BPCE inattendu")
    jobs = []
    for row in rows:
        url = str((row or {}).get("url") or "")
        if not url.startswith("https://recrutement.bpce.fr/job/"):
            continue
        # The feed has no publication date (only a refresh timestamp): Em Jobs dates it on first sight.
        jobs.append(RawJob(
            title=plain_text(row.get("title") or ""),
            locations=[", ".join(str(row[k]) for k in ("city", "state", "country") if row.get(k))],
            url=url, employment=str(row.get("jobtype") or ""), company=str(row.get("organization") or ""),
            description=plain_text(row.get("description") or "")))
    return jobs


def talentsoft(source: Source, session: requests.Session) -> list[RawJob]:
    """Talent-soft (Cegid) career sites: slug is the host, e.g. jobs.ca-cib.com. Reads the whole listing."""
    base = f"https://{source.slug}"
    found: dict[str, RawJob] = {}
    card = re.compile(r'<a\s[^>]*href="(/offre-de-emploi/emploi-[^"]*_(\d+)\.aspx)"[^>]*>(.*?)</a>.*?<ul[^>]*>(.*?)</ul>', re.S)
    for page in range(1, 40):
        text = _html(session, f"{base}/offre-de-emploi/liste-offres.aspx", params={"page": page, "LCID": 1036})
        total = re.search(r"\((\d+)\s+offres?,\s+page", text)
        if not total:
            raise ValueError("liste Talent-soft inattendue")
        before = len(found)
        for path, identity, title, tags in card.findall(text):
            items = [plain_text(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", tags, re.S)]

            def details(job: RawJob) -> None:
                detail = _html(session, job.url)
                start = detail.find('class="JobDescription">')
                job.description = plain_text(detail[start + 23:] if start >= 0 else detail)[:20000]

            found.setdefault(identity, RawJob(title=plain_text(title), locations=[", ".join(filter(None, items[1:]))],
                                              url=base + path, employment=items[0] if items else "", details=details))
        # An out-of-range page silently shows page 1 again: stop when nothing new appears.
        if len(found) >= int(total[1]) or len(found) == before:
            break
    return list(found.values())


def avature(source: Source, session: requests.Session) -> list[RawJob]:
    """Avature portals: slug is host/portal, e.g. bloomberg.avature.net/careers.

    The portal serves 12 offers per page whatever size is asked; its whole catalogue
    (about 300 offers) costs fewer pages than the keyword searches, which match descriptions.
    """
    host, portal = source.slug.split("/")
    jobs: dict[str, RawJob] = {}
    for offset in range(0, 3000, 12):
        text = _html(session, f"https://{host}/{portal}/SearchJobs/", params={"jobRecordsPerPage": 12, "jobOffset": offset})
        total = re.search(r'aria-label="(\d+) results"', text)
        if not total:
            raise ValueError("catalogue Avature inattendu")
        rows = re.findall(r"<article\b[^>]*article--result\b.*?</article>", text, re.S)
        for row in rows:
            link = re.search(rf'href="(https://{re.escape(host)}/{portal}/JobDetail/[^"]+/(\d+))"[^>]*>(.*?)</a>', row, re.S)
            place = re.search(r"list-item-location[^>]*>(.*?)</span>", row, re.S)
            if not link or link[2] in jobs:
                continue

            def details(job: RawJob) -> None:
                blocks = re.findall(r"<article\b[^>]*article--details\b[^>]*>(.*?)</article>", _html(session, job.url), re.S)
                job.description = plain_text(" ".join(blocks[1:]))[:20000]

            jobs[link[2]] = RawJob(title=plain_text(link[3]), locations=[plain_text(place[1]) if place else ""],
                                   url=link[1], details=details)
        if not rows or offset + 12 >= int(total[1]):
            break
    return list(jobs.values())


def cagroup(source: Source, session: requests.Session) -> list[RawJob]:
    """groupecreditagricole.jobs keyword search; each offer carries its entity (Amundi, CACEIS, LCL...)."""
    found: dict[str, RawJob] = {}
    for term in SEARCH_TERMS:
        for page in range(1, 20):
            try:
                text = _html(session, f"https://{source.slug}/fr/nos-offres/mot-cles/{quote(term.replace(' ', '-'))}/page/{page}/")
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code == 404:
                    break  # no result for this term, or past its last page
                raise
            if not re.search(r"offres? disponibles?", text):
                raise ValueError("recherche groupecreditagricole.jobs inattendue")
            cards = re.findall(r'<article class="card offer[^"]*"(.*?)>(.*?)</article>', text, re.S)
            for attributes, body in cards:
                link = re.search(rf'href="(https://{re.escape(source.slug)}/fr/nos-offres-emploi/[^"]+)"', body)
                if not link or link[1] in found:
                    continue

                def attr(name: str, attributes=attributes) -> str:
                    match = re.search(rf'data-gtm-{name}="([^"]*)"', attributes)
                    return html.unescape(match[1]).strip() if match else ""

                def details(job: RawJob) -> None:
                    posting = _jsonld_posting(_html(session, job.url))
                    job.description = plain_text(posting.get("description") or "")
                    job.published = iso_day(_fr_day(str(posting.get("datePosted") or "")))

                found[link[1]] = RawJob(title=attr("jobTitle"), locations=[attr("jobCity")], url=link[1],
                                        employment=attr("jobContract"), company=attr("jobEntity"), details=details)
            if len(cards) < 33:
                break
    return list(found.values())


CONNECTORS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby,
              "smartrecruiters": smartrecruiters, "workday": workday, "oracle": oracle,
              "successfactors": successfactors, "teamtailor": teamtailor, "workable": workable,
              "recruitee": recruitee, "socgen": socgen, "bpce": bpce, "talentsoft": talentsoft,
              "avature": avature, "cagroup": cagroup}
