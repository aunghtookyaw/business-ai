from dataclasses import dataclass

from tools.master_data import normalize_name


@dataclass(frozen=True)
class RelinkPlan:
    total: int
    matched: int
    unmatched: int
    blank: int
    already_linked: int
    to_insert: tuple[tuple[int, int], ...]
    conflicts: tuple[dict, ...]
    unmatched_values: tuple[tuple[str, int], ...]
    duplicate_master_names: tuple[tuple[str, tuple[dict, ...]], ...]

    @property
    def insert_count(self):
        return len(self.to_insert)

    def to_dict(self):
        return {
            "total": self.total,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "blank": self.blank,
            "already_linked": self.already_linked,
            "to_insert": self.insert_count,
            "conflicts": list(self.conflicts),
            "unmatched_values": [
                {"value": value, "row_count": count}
                for value, count in self.unmatched_values
            ],
            "duplicate_master_names": [
                {"normalized_name": normalized, "masters": list(rows)}
                for normalized, rows in self.duplicate_master_names
            ],
        }


def plan_relinks(transaction_rows, master_rows, existing_links):
    master_by_normalized, duplicate_masters = _master_lookup(master_rows)
    existing_by_transaction = _existing_lookup(existing_links)

    matched = 0
    unmatched = 0
    blank = 0
    already_linked = 0
    to_insert = []
    conflicts = []
    unmatched_values = {}

    for row in transaction_rows:
        transaction_id = int(row["id"])
        value = row.get("value")
        normalized = normalize_name(value)
        if not normalized:
            blank += 1
            continue
        master = master_by_normalized.get(normalized)
        if not master:
            unmatched += 1
            display_value = str(value or "").strip()
            unmatched_values[display_value] = unmatched_values.get(display_value, 0) + 1
            continue

        matched += 1
        master_id = int(master["id"])
        existing_master_ids = existing_by_transaction.get(transaction_id, set())
        if master_id in existing_master_ids:
            already_linked += 1
        elif existing_master_ids:
            conflicts.append({
                "transaction_id": transaction_id,
                "value": value,
                "target_master_id": master_id,
                "existing_master_ids": sorted(existing_master_ids),
            })
        else:
            to_insert.append((transaction_id, master_id))

    return RelinkPlan(
        total=len(transaction_rows),
        matched=matched,
        unmatched=unmatched,
        blank=blank,
        already_linked=already_linked,
        to_insert=tuple(to_insert),
        conflicts=tuple(conflicts),
        unmatched_values=tuple(
            sorted(unmatched_values.items(), key=lambda item: (-item[1], item[0].lower()))
        ),
        duplicate_master_names=tuple(
            sorted(duplicate_masters.items(), key=lambda item: item[0])
        ),
    )


def _master_lookup(master_rows):
    master_by_normalized = {}
    duplicate_masters = {}
    for row in master_rows:
        normalized = normalize_name(row.get("value"))
        if not normalized:
            continue
        master = {"id": int(row["id"]), "value": row.get("value")}
        if normalized in master_by_normalized:
            duplicate_masters.setdefault(normalized, [master_by_normalized[normalized]]).append(master)
            continue
        master_by_normalized[normalized] = master

    for normalized in duplicate_masters:
        master_by_normalized.pop(normalized, None)

    return master_by_normalized, {
        normalized: tuple(rows) for normalized, rows in duplicate_masters.items()
    }


def _existing_lookup(existing_links):
    existing = {}
    for row in existing_links:
        transaction_id = int(row["transaction_id"])
        master_id = int(row["master_id"])
        existing.setdefault(transaction_id, set()).add(master_id)
    return existing


def filter_plan_to_transaction_ids(plan, transaction_ids):
    transaction_ids = {int(transaction_id) for transaction_id in transaction_ids}
    if not transaction_ids:
        return plan
    return RelinkPlan(
        total=plan.total,
        matched=plan.matched,
        unmatched=plan.unmatched,
        blank=plan.blank,
        already_linked=plan.already_linked,
        to_insert=tuple(
            pair for pair in plan.to_insert if int(pair[0]) in transaction_ids
        ),
        conflicts=tuple(
            conflict
            for conflict in plan.conflicts
            if int(conflict["transaction_id"]) in transaction_ids
        ),
        unmatched_values=plan.unmatched_values,
        duplicate_master_names=plan.duplicate_master_names,
    )
