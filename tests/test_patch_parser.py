from pr_triage_prompt.analyzers.patch import parse_patch


def test_added_file_records_every_line_as_added() -> None:
    patch = "@@ -0,0 +1,3 @@\n+alpha\n+beta\n+gamma\n"
    result = parse_patch(patch)
    assert result.added_line_numbers == {1, 2, 3}
    assert result.removed_line_numbers == set()


def test_modification_captures_both_sides() -> None:
    patch = (
        "@@ -10,4 +10,4 @@\n"
        " unchanged\n"
        "-old_one\n"
        "+new_one\n"
        " unchanged_two\n"
        "-old_two\n"
        "+new_two\n"
    )
    result = parse_patch(patch)
    assert result.added_line_numbers == {11, 13}
    assert result.removed_line_numbers == {11, 13}


def test_multi_hunk_tracks_independent_offsets() -> None:
    patch = (
        "@@ -1,2 +1,2 @@\n"
        " keep\n"
        "-old\n"
        "+newA\n"
        "@@ -50,2 +50,2 @@\n"
        " keep50\n"
        "-old50\n"
        "+newB\n"
    )
    result = parse_patch(patch)
    assert result.added_line_numbers == {2, 51}
    assert result.removed_line_numbers == {2, 51}
    assert len(result.hunks) == 2


def test_touches_post_range_helper() -> None:
    patch = "@@ -0,0 +1,3 @@\n+a\n+b\n+c\n"
    result = parse_patch(patch)
    assert result.touches_post_range(1, 3)
    assert result.touches_post_range(2, 2)
    assert not result.touches_post_range(10, 20)


def test_no_newline_marker_ignored() -> None:
    patch = (
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "\\ No newline at end of file\n"
        "+new\n"
    )
    result = parse_patch(patch)
    assert result.added_line_numbers == {1}
    assert result.removed_line_numbers == {1}


def test_empty_patch_yields_empty() -> None:
    assert parse_patch("").hunks == []


def test_single_line_hunk_header_defaults_len_to_one() -> None:
    patch = "@@ -5 +5 @@\n-x\n+y\n"
    result = parse_patch(patch)
    assert result.hunks[0].pre_len == 1
    assert result.hunks[0].post_len == 1
    assert result.added_line_numbers == {5}
    assert result.removed_line_numbers == {5}
