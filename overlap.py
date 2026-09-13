def get_overlap_window(fund_ids, data):
    
    dates = data['dates']
    funds_by_id = {f['id']: f for f in data['funds']}

    missing = [fid for fid in fund_ids if fid not in funds_by_id]
    if missing:
        raise KeyError(f"Unknown fund id(s): {missing}")

    selected = [funds_by_id[fid] for fid in fund_ids]

    valid_indices = [
        i for i in range(len(dates))
        if all(f['returns'][i] is not None for f in selected)
    ]

    if not valid_indices:
        return None

    start_idx, end_idx = valid_indices[0], valid_indices[-1]
    expected_count = end_idx - start_idx + 1

    if len(valid_indices) != expected_count:
        valid_set = set(valid_indices)
        gap_indices = [i for i in range(start_idx, end_idx + 1) if i not in valid_set]
        raise ValueError(
            f"Overlap window for {fund_ids} is not contiguous — "
            f"gaps at dates: {[dates[i] for i in gap_indices]}. "
            f"This is unexpected post-cleanup; investigate before proceeding."
        )

    return {
        "fund_ids": fund_ids,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "start_date": dates[start_idx],
        "end_date": dates[end_idx],
        "n_months": expected_count,
    }


if __name__ == "__main__":
    import json
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "funds_aligned.json"
    with open(path, 'r') as f:
        data = json.load(f)

    # Quick manual sanity checks - adjust fund ids to ones you know the
    # expected date ranges for, and confirm the output matches.
    all_ids = [f['id'] for f in data['funds']]

    print("All funds together:")
    print(get_overlap_window(all_ids, data))

    print("\nFirst two funds:")
    print(get_overlap_window(all_ids[:2], data))

    print("\nSingle fund (119091, the one that had the gap):")
    print(get_overlap_window([119091], data))