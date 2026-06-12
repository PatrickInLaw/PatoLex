"""append_body_entries.py -- merge the 74 1913-1975 image-only BODY volumes
into the LIVE 5090 production_queue_state.json, PRESERVING each entry's 'pdf'
field. Atomic: same exclusive lock the workers use, .tmp then os.replace.
Idempotent by label -- never alters/deletes existing entries; skips labels
already present. Generated from manifest_1913_1975.json (derived from
corpus_page_counts.csv, is_body=TRUE, year 1913..1975)."""
import os, sys, json, time, errno
from pathlib import Path

import config

S = Path(config.path_for("data_root"))
Q = S / "production_queue_state.json"
L = S / "production_queue_state.lock"

NEW = [
    {
        "label": "1913-statutes",
        "pdf": "1913_Statutes.pdf",
        "year": 1913,
        "status": "pending"
    },
    {
        "label": "1915-vol1-chapters",
        "pdf": "1915_Vol1_Chapters.pdf",
        "year": 1915,
        "status": "pending"
    },
    {
        "label": "1917-vol1-chapters",
        "pdf": "1917_Vol1_Chapters.pdf",
        "year": 1917,
        "status": "pending"
    },
    {
        "label": "1919-vol1-chapters",
        "pdf": "1919_Vol1_Chapters.pdf",
        "year": 1919,
        "status": "pending"
    },
    {
        "label": "1921-vol1-chapters",
        "pdf": "1921_Vol1_Chapters.pdf",
        "year": 1921,
        "status": "pending"
    },
    {
        "label": "1923-vol1-chapters",
        "pdf": "1923_Vol1_Chapters.pdf",
        "year": 1923,
        "status": "pending"
    },
    {
        "label": "1925-vol1-chapters",
        "pdf": "1925_Vol1_Chapters.pdf",
        "year": 1925,
        "status": "pending"
    },
    {
        "label": "1927-vol1-26chapters",
        "pdf": "1927_Vol1_26Chapters.pdf",
        "year": 1927,
        "status": "pending"
    },
    {
        "label": "1927-vol1-chapters",
        "pdf": "1927_Vol1_Chapters.pdf",
        "year": 1927,
        "status": "pending"
    },
    {
        "label": "1929-vol1-28chapters",
        "pdf": "1929_Vol1_28Chapters.pdf",
        "year": 1929,
        "status": "pending"
    },
    {
        "label": "1929-vol1-29chapters",
        "pdf": "1929_Vol1_29Chapters.pdf",
        "year": 1929,
        "status": "pending"
    },
    {
        "label": "1931-vol1-chapters",
        "pdf": "1931_Vol1_Chapters.pdf",
        "year": 1931,
        "status": "pending"
    },
    {
        "label": "1933-vol1-chapters",
        "pdf": "1933_Vol1_Chapters.pdf",
        "year": 1933,
        "status": "pending"
    },
    {
        "label": "1935-vol1-34chapters",
        "pdf": "1935_Vol1_34Chapters.pdf",
        "year": 1935,
        "status": "pending"
    },
    {
        "label": "1935-vol1-chapters",
        "pdf": "1935_Vol1_Chapters.pdf",
        "year": 1935,
        "status": "pending"
    },
    {
        "label": "1937-vol1-chapters",
        "pdf": "1937_Vol1_Chapters.pdf",
        "year": 1937,
        "status": "pending"
    },
    {
        "label": "1938-vol1-chapters",
        "pdf": "1938_Vol1_Chapters.pdf",
        "year": 1938,
        "status": "pending"
    },
    {
        "label": "1939-vol1-chapters",
        "pdf": "1939_Vol1_Chapters.pdf",
        "year": 1939,
        "status": "pending"
    },
    {
        "label": "1941-vol1-41chapters",
        "pdf": "1941_Vol1_41Chapters.pdf",
        "year": 1941,
        "status": "pending"
    },
    {
        "label": "1943-vol1-42chapters",
        "pdf": "1943_Vol1_42Chapters.pdf",
        "year": 1943,
        "status": "pending"
    },
    {
        "label": "1943-vol1-chapters",
        "pdf": "1943_Vol1_Chapters.pdf",
        "year": 1943,
        "status": "pending"
    },
    {
        "label": "1945-vol1-chapters",
        "pdf": "1945_Vol1_Chapters.pdf",
        "year": 1945,
        "status": "pending"
    },
    {
        "label": "1947-vol1-46chapters",
        "pdf": "1947_Vol1_46Chapters.pdf",
        "year": 1947,
        "status": "pending"
    },
    {
        "label": "1947-vol1-chapters",
        "pdf": "1947_Vol1_Chapters.pdf",
        "year": 1947,
        "status": "pending"
    },
    {
        "label": "1948-vol1-chapters",
        "pdf": "1948_Vol1_Chapters.pdf",
        "year": 1948,
        "status": "pending"
    },
    {
        "label": "1949-vol1-49chapters-prior",
        "pdf": "1949_Vol1_49Chapters_prior.pdf",
        "year": 1949,
        "status": "pending"
    },
    {
        "label": "1949-vol1-chapters",
        "pdf": "1949_Vol1_Chapters.pdf",
        "year": 1949,
        "status": "pending"
    },
    {
        "label": "1950-vol1-chapters",
        "pdf": "1950_Vol1_Chapters.pdf",
        "year": 1950,
        "status": "pending"
    },
    {
        "label": "1951-vol1-50chapters",
        "pdf": "1951_Vol1_50Chapters.pdf",
        "year": 1951,
        "status": "pending"
    },
    {
        "label": "1951-vol1-chapters",
        "pdf": "1951_Vol1_Chapters.pdf",
        "year": 1951,
        "status": "pending"
    },
    {
        "label": "1951-vol2-chapters",
        "pdf": "1951_Vol2_Chapters.pdf",
        "year": 1951,
        "status": "pending"
    },
    {
        "label": "1953-vol1-52chapters",
        "pdf": "1953_Vol1_52Chapters.pdf",
        "year": 1953,
        "status": "pending"
    },
    {
        "label": "1953-vol1-chapters",
        "pdf": "1953_Vol1_Chapters.pdf",
        "year": 1953,
        "status": "pending"
    },
    {
        "label": "1953-vol2-chapters",
        "pdf": "1953_Vol2_Chapters.pdf",
        "year": 1953,
        "status": "pending"
    },
    {
        "label": "1955-vol1-54chapters",
        "pdf": "1955_Vol1_54Chapters.pdf",
        "year": 1955,
        "status": "pending"
    },
    {
        "label": "1955-vol1-55chapters",
        "pdf": "1955_Vol1_55Chapters.pdf",
        "year": 1955,
        "status": "pending"
    },
    {
        "label": "1955-vol2-chapters",
        "pdf": "1955_Vol2_Chapters.pdf",
        "year": 1955,
        "status": "pending"
    },
    {
        "label": "1957-vol1-56chapters",
        "pdf": "1957_Vol1_56Chapters.pdf",
        "year": 1957,
        "status": "pending"
    },
    {
        "label": "1957-vol1-57chapters",
        "pdf": "1957_Vol1_57Chapters.pdf",
        "year": 1957,
        "status": "pending"
    },
    {
        "label": "1957-vol2-57chapters",
        "pdf": "1957_Vol2_57Chapters.pdf",
        "year": 1957,
        "status": "pending"
    },
    {
        "label": "1959-vol1-58chapters",
        "pdf": "1959_Vol1_58Chapters.pdf",
        "year": 1959,
        "status": "pending"
    },
    {
        "label": "1959-vol1-59chapters",
        "pdf": "1959_Vol1_59Chapters.pdf",
        "year": 1959,
        "status": "pending"
    },
    {
        "label": "1959-vol2-chapters",
        "pdf": "1959_Vol2_Chapters.pdf",
        "year": 1959,
        "status": "pending"
    },
    {
        "label": "1961-vol1-60chapters",
        "pdf": "1961_Vol1_60Chapters.pdf",
        "year": 1961,
        "status": "pending"
    },
    {
        "label": "1961-vol1-61chapters",
        "pdf": "1961_Vol1_61Chapters.pdf",
        "year": 1961,
        "status": "pending"
    },
    {
        "label": "1961-vol2-chapters",
        "pdf": "1961_Vol2_Chapters.pdf",
        "year": 1961,
        "status": "pending"
    },
    {
        "label": "1963-vol1-62chapters",
        "pdf": "1963_Vol1_62Chapters.pdf",
        "year": 1963,
        "status": "pending"
    },
    {
        "label": "1963-vol1-63chapters",
        "pdf": "1963_Vol1_63Chapters.pdf",
        "year": 1963,
        "status": "pending"
    },
    {
        "label": "1963-vol2-chapters",
        "pdf": "1963_Vol2_Chapters.pdf",
        "year": 1963,
        "status": "pending"
    },
    {
        "label": "1965-vol1-64chapters",
        "pdf": "1965_Vol1_64Chapters.pdf",
        "year": 1965,
        "status": "pending"
    },
    {
        "label": "1965-vol1-65chapters",
        "pdf": "1965_Vol1_65Chapters.pdf",
        "year": 1965,
        "status": "pending"
    },
    {
        "label": "1965-vol2",
        "pdf": "1965_Vol2.pdf",
        "year": 1965,
        "status": "pending"
    },
    {
        "label": "1965-vol3-chapters",
        "pdf": "1965_Vol3_Chapters.pdf",
        "year": 1965,
        "status": "pending"
    },
    {
        "label": "1966-vol1-chapters",
        "pdf": "1966_Vol1_Chapters.pdf",
        "year": 1966,
        "status": "pending"
    },
    {
        "label": "1967-vol1-chapters",
        "pdf": "1967_Vol1_Chapters.pdf",
        "year": 1967,
        "status": "pending"
    },
    {
        "label": "1967-vol2",
        "pdf": "1967_Vol2.pdf",
        "year": 1967,
        "status": "pending"
    },
    {
        "label": "1967-vol3-chapters",
        "pdf": "1967_Vol3_Chapters.pdf",
        "year": 1967,
        "status": "pending"
    },
    {
        "label": "1968-vol1-chapters",
        "pdf": "1968_Vol1_Chapters.pdf",
        "year": 1968,
        "status": "pending"
    },
    {
        "label": "1968-vol2-chapters",
        "pdf": "1968_Vol2_Chapters.pdf",
        "year": 1968,
        "status": "pending"
    },
    {
        "label": "1969-vol1-chapters",
        "pdf": "1969_Vol1_Chapters.pdf",
        "year": 1969,
        "status": "pending"
    },
    {
        "label": "1969-vol2-chapters",
        "pdf": "1969_Vol2_Chapters.pdf",
        "year": 1969,
        "status": "pending"
    },
    {
        "label": "1970-vol1-chapters",
        "pdf": "1970_Vol1_Chapters.pdf",
        "year": 1970,
        "status": "pending"
    },
    {
        "label": "1970-vol2-chapters",
        "pdf": "1970_Vol2_Chapters.pdf",
        "year": 1970,
        "status": "pending"
    },
    {
        "label": "1971-vol1-chapters",
        "pdf": "1971_Vol1_Chapters.pdf",
        "year": 1971,
        "status": "pending"
    },
    {
        "label": "1971-vol2",
        "pdf": "1971_Vol2.pdf",
        "year": 1971,
        "status": "pending"
    },
    {
        "label": "1971-vol3-chapters",
        "pdf": "1971_Vol3_Chapters.pdf",
        "year": 1971,
        "status": "pending"
    },
    {
        "label": "1972-vol1-chapters",
        "pdf": "1972_Vol1_Chapters.pdf",
        "year": 1972,
        "status": "pending"
    },
    {
        "label": "1972-vol2-chapters",
        "pdf": "1972_Vol2_Chapters.pdf",
        "year": 1972,
        "status": "pending"
    },
    {
        "label": "1973-vol1-chapters",
        "pdf": "1973_Vol1_Chapters.pdf",
        "year": 1973,
        "status": "pending"
    },
    {
        "label": "1973-vol2-chapters",
        "pdf": "1973_Vol2_Chapters.pdf",
        "year": 1973,
        "status": "pending"
    },
    {
        "label": "1974-vol1-chapters",
        "pdf": "1974_Vol1_Chapters.pdf",
        "year": 1974,
        "status": "pending"
    },
    {
        "label": "1974-vol2-chapters",
        "pdf": "1974_Vol2_Chapters.pdf",
        "year": 1974,
        "status": "pending"
    },
    {
        "label": "1975-vol1-chapters",
        "pdf": "1975_Vol1_Chapters.pdf",
        "year": 1975,
        "status": "pending"
    },
    {
        "label": "1975-vol2-chapters",
        "pdf": "1975_Vol2_Chapters.pdf",
        "year": 1975,
        "status": "pending"
    }
]


def lock():
    while True:
        try:
            fd = os.open(str(L), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            return
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            if time.time() - os.path.getmtime(str(L)) > 60:
                os.remove(str(L))
                continue
            time.sleep(0.15)


def unlock():
    try:
        os.remove(str(L))
    except OSError:
        pass


def main():
    lock()
    try:
        st = json.loads(Q.read_text(encoding="utf-8-sig"))
        have = {v["label"] for v in st["volumes"]}
        added = []
        for item in NEW:
            if item["label"] in have:
                continue
            st["volumes"].append(dict(item))
            added.append(item["label"])
        st["volumes"].sort(key=lambda v: (v["year"], v["label"]))
        tmp = Q.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(Q))
        print("APPENDED_COUNT " + str(len(added)))
        print("APPENDED " + json.dumps(added))
        print("TOTAL " + str(len(st["volumes"])))
    finally:
        unlock()


if __name__ == "__main__":
    main()
