from src.synthesize import (_overall_verdict, build_comment, build_ping,
                            build_report, find_report_comment, post_comment,
                            post_ping, summary_counts)

SNAPSHOT = {
    "owner": "demo", "repo": "app", "pr": 7,
    "title": "Add checkout flow", "author": "dev1", "base": "main", "head": "x",
    "labels": ["feature"], "body": "Adds checkout.",
    "files": [{"filename": "src/checkout.py", "status": "added",
               "additions": 50, "deletions": 0, "patch": ""}],
    "commits": [{"sha": "a", "message": "feat"}],
    "threads": [{"path": "src/checkout.py", "line": 3, "author": "r1",
                 "body": "Missing validation", "resolved": False, "outdated": False}],
}

CLAIMS = [
    {"id": "C1", "text": "Adds checkout", "category": "feature",
     "files": ["src/checkout.py"], "docs": []},
]

FINDINGS = {
    "claims": [{"id": "C1", "status": "PASS", "evidence": ["src/checkout.py:1"], "note": ""}],
    "docs": [{"path": "docs/payment.md", "status": "WRONG", "what": "doc says retry 3, code retries 5"}],
    "impact": [{"requirement": "REQ-1 checkout", "impact": "CHANGED", "detail": "new flow"}],
    "threads": [{"text": "Missing validation", "status": "STILL_VALID", "note": "not fixed yet"}],
    "unresolved_questions": [],
}

ANSWERS = [{"question": "Is the payment doc wrong?", "kind": "doc", "answer": "y"}]


def test_build_report_vn(tmp_path):
    report = build_report(SNAPSHOT, CLAIMS, FINDINGS, ANSWERS, tmp_path)
    assert "## Đánh giá" in report
    assert "Trùng khớp" in report
    assert "Sai lệch" in report
    assert "REQ-1" in report
    assert "not fixed yet" in report
    assert (tmp_path / "report.md").exists()


def test_build_comment_en_has_marker_and_verdict():
    comment = build_comment(SNAPSHOT, CLAIMS, FINDINGS, ANSWERS)
    assert "<!-- harness-pr-review -->" in comment
    assert "## DUT AI PR Review" in comment
    assert "Trùng khớp" in comment
    assert "docs/payment.md" in comment
    assert "Còn hiệu lực" in comment


def test_build_comment_embeds_full_report(tmp_path):
    report = build_report(SNAPSHOT, CLAIMS, FINDINGS, ANSWERS, tmp_path)
    comment = build_comment(SNAPSHOT, CLAIMS, FINDINGS, ANSWERS,
                            report_content=report)
    assert "<!-- harness-pr-review -->" in comment
    assert "Kết quả đánh giá:" in comment
    assert "REQ-1" in comment
    assert "Trùng khớp" in comment


def test_build_comment_html_sections():
    comment = build_comment(SNAPSHOT, CLAIMS, FINDINGS, ANSWERS)
    assert "Yêu cầu" in comment
    assert "Tài liệu so với thực tế" in comment
    assert "Tác động yêu cầu" in comment
    assert "Luồng bình luận review" in comment
    assert "Nhật ký xác nhận" in comment
    assert "<details" in comment


def test_post_comment_updates_via_gh(monkeypatch):
    existing = [{"id": 42, "body": "<!-- harness-pr-review --> old"}]
    seen = []
    monkeypatch.setattr("src.synthesize.run_gh",
                        lambda args, **kw: (existing if "GET" in args else None))

    def fake_gh(args, **kw):
        seen.append(args)
        return {"id": 42}

    posted = post_comment("demo", "app", 7, "new", gh=fake_gh,
                          list_comments=lambda: existing)
    assert posted is False
    # body được gửi qua temp file (-F body=@...) để tránh ARG_MAX
    assert seen[0][:4] == ["api", "repos/demo/app/issues/comments/42",
                           "-X", "PATCH"]
    assert seen[0][4] == "-F"
    assert seen[0][5].startswith("body=@")


def test_post_comment_posts_when_no_marker(monkeypatch):
    posted = post_comment("demo", "app", 7, "new",
                          gh=lambda args, **kw: {"id": 1},
                          list_comments=lambda: [{"body": "other"}])
    assert posted is True


def test_build_report_escapes_cells(tmp_path):
    findings = {
        "claims": [{"id": "C1", "status": "PASS", "evidence": ["a.py:1|2"],
                    "note": "note\nwith | pipe"}],
        "docs": [{"path": "docs/a.md", "status": "WRONG", "what": "diff|erence\nnewline"}],
        "impact": [{"requirement": "REQ-1|a", "impact": "CHANGED", "detail": "de\ntail"}],
        "threads": [{"text": "comment\nwith | pipe", "status": "STILL_VALID", "note": "no\ntes|1"}],
        "unresolved_questions": [],
    }
    report = build_report(SNAPSHOT, CLAIMS, findings, [], tmp_path)
    assert "\\|" in report
    assert "<br>" in report
    assert "Nội dung" in report
    assert "Adds checkout" in report
    comment = build_comment(SNAPSHOT, CLAIMS, findings, [])
    assert "comment" in comment
    assert "no" in comment  # HTML-escaped, không còn raw "| pipe"


def test_no_claims_verdict(tmp_path):
    findings = {"claims": [], "docs": [], "impact": [], "threads": [],
                "unresolved_questions": []}
    report = build_report(SNAPSHOT, [], findings, [], tmp_path)
    assert "Không có yêu cầu nào" in report
    comment = build_comment(SNAPSHOT, [], findings, [])
    assert "Không có yêu cầu nào" in comment


def test_verdict_precedence():
    assert _overall_verdict({"claims": [{"status": "PASS"}, {"status": "FAIL"}]}) == "CONTRADICTED"
    assert _overall_verdict({"claims": [{"status": "PASS"}, {"status": "UNVERIFIED"}]}) == "PARTIAL"


def test_post_comment_default_lists_paginated_and_posts_dash_f():
    seen = []

    def fake_gh(args, **kw):
        seen.append(args)
        return []

    post_comment("demo", "app", 7, "body", gh=fake_gh)
    assert "--paginate" in seen[0]
    # body qua temp file để tránh ARG_MAX
    assert "-F" in seen[1]
    assert seen[1][seen[1].index("-F") + 1].startswith("body=@")


def test_build_comment_summary_badges():
    comment = build_comment(SNAPSHOT, CLAIMS, FINDINGS, ANSWERS)
    assert "Rủi ro tìm thấy:" in comment
    assert "Lỗi tài liệu:" in comment


def _snap(**kw):
    base = {"owner": "o", "repo": "r", "pr": 9, "title": "t", "body": "",
            "author": "a", "base": "main", "head": "x", "head_sha": "1930e24abc",
            "labels": [], "files": [], "commits": [], "threads": []}
    base.update(kw)
    return base


EMPTY = {"claims": [], "docs": [], "impact": [], "threads": [],
         "unresolved_questions": []}


def test_comment_states_the_review_finished():
    """Comment được PATCH tại chỗ nên GitHub không báo — phải tự nói là đã xong."""
    body = build_comment(_snap(), [], EMPTY, [], rounds=3,
                         completed_at="2026-08-18 11:02 UTC")
    assert "Hoàn thành review" in body
    assert "2026-08-18 11:02 UTC" in body     # biết là mới hay cũ
    assert "vòng 3" in body
    assert "`1930e24`" in body                 # biết review đúng commit nào
    assert "cập nhật trực tiếp tại chỗ" in body # biết vì sao không có notification


def test_completion_line_sits_above_the_collapsed_sections():
    """Phải nằm trên các <details> vì chúng mặc định đóng."""
    body = build_comment(_snap(), CLAIMS, FINDINGS, [], completed_at="x")
    assert body.index("Hoàn thành review") < body.index("<details")


def _completion_line_of(body: str) -> str:
    """Chỉ lấy dòng completion, không assert trên cả comment."""
    return next(ln for ln in body.splitlines() if ln.startswith("✅"))


def test_completion_line_survives_missing_metadata():
    """Không có rounds.txt / head_sha → vẫn báo hoàn thành, không vỡ."""
    body = build_comment(_snap(head_sha=""), [], EMPTY, [], rounds=None,
                         completed_at="2026-08-18 11:02 UTC")
    line = _completion_line_of(body)
    assert "Hoàn thành review" in line
    assert "2026-08-18 11:02 UTC" in line
    assert "vòng" not in line
    assert "commit `" not in line


def test_completion_timestamp_defaults_to_now():
    import time

    body = build_comment(_snap(), [], EMPTY, [])
    assert time.strftime("%Y-%m-%d", time.gmtime()) in body
    assert "UTC" in body


# --- round ping -------------------------------------------------------------

PING_FINDINGS = {
    "claims": [{"status": "PASS"}] * 12 + [{"status": "PARTIAL"}]
              + [{"status": "UNVERIFIED"}] * 2,
    "docs": [{"status": "STALE"}, {"status": "WRONG"}, {"status": "MATCH"}],
    "impact": [{"impact": "RISK"}, {"impact": "CHANGED"}],
    "threads": [], "unresolved_questions": [],
}


def test_ping_marker_is_not_confused_with_main_marker():
    """post_comment PATCH comment đầu tiên chứa MARKER.

    Nếu MARKER là substring của PING_MARKER, báo cáo đầy đủ sẽ đè lên ping và
    ping vòng trước biến mất. Ràng buộc này phải được ghim lại.
    """
    from src.synthesize import MARKER, PING_MARKER

    assert MARKER not in PING_MARKER
    assert PING_MARKER not in MARKER
    ping = build_ping(_snap(), PING_FINDINGS, rounds=1, completed_at="t")
    assert MARKER not in ping


def test_ping_carries_the_headline_numbers():
    ping = build_ping(_snap(), PING_FINDINGS, rounds=3,
                      completed_at="2026-08-18 11:02 UTC")
    assert "vòng 3" in ping
    assert "`1930e24`" in ping            # commit đã review
    assert "2026-08-18 11:02 UTC" in ping
    assert "**2** rủi ro" in ping         # 1 PARTIAL + 1 RISK impact
    assert "**2** lỗi tài liệu" in ping   # STALE + WRONG, MATCH không tính
    assert "15 yêu cầu" in ping
    assert "12 trùng khớp" in ping and "1 một phần" in ping and "2 chưa xác minh" in ping


def test_ping_numbers_match_the_full_comment():
    """Ping và comment đầy đủ phải cùng một nguồn số, không được lệch."""
    counts = summary_counts(PING_FINDINGS)
    body = build_comment(_snap(), [], PING_FINDINGS, [], completed_at="t")
    ping = build_ping(_snap(), PING_FINDINGS, completed_at="t")
    assert f"Rủi ro tìm thấy: {counts['risks']}" in body
    assert f"**{counts['risks']}** rủi ro" in ping


def test_ping_posts_a_new_comment_every_round():
    """Ping KHÔNG idempotent — comment mới mỗi vòng mới có notification."""
    seen = []
    post_ping("demo", "app", 7, "body-round-1", gh=lambda a, **k: seen.append(a))
    post_ping("demo", "app", 7, "body-round-2", gh=lambda a, **k: seen.append(a))
    assert len(seen) == 2
    for args in seen:
        assert args[:2] == ["api", "repos/demo/app/issues/7/comments"]
        assert "PATCH" not in args


def test_find_report_comment_ignores_pings():
    from src.synthesize import MARKER, PING_MARKER

    comments = [{"id": 1, "body": f"ping\n{PING_MARKER}", "html_url": "u1"},
                {"id": 2, "body": f"report\n{MARKER}", "html_url": "u2"}]
    found = find_report_comment("demo", "app", 7,
                                list_comments=lambda: comments)
    assert found["id"] == 2


def test_post_comment_updates_report_not_ping():
    """Có ping trong thread → PATCH vẫn phải trúng comment báo cáo."""
    from src.synthesize import MARKER, PING_MARKER

    comments = [{"id": 1, "body": f"ping\n{PING_MARKER}"},
                {"id": 2, "body": f"report\n{MARKER}"}]
    seen = []
    posted = post_comment("demo", "app", 7, "new", gh=lambda a, **k: seen.append(a),
                          list_comments=lambda: comments)
    assert posted is False
    assert "repos/demo/app/issues/comments/2" in seen[0][1]


INFERRED_CLAIMS = [
    {"id": "C1", "text": "Thử lại thanh toán tối đa 5 lần", "category": "bugfix",
     "files": ["src/payment.py"], "docs": [], "source": "inferred"},
]


def test_inferred_claims_get_their_own_verdict():
    passing = {"claims": [{"id": "C1", "status": "PASS"}]}
    assert _overall_verdict(passing, INFERRED_CLAIMS) == "NO DESCRIPTION"

    failing = {"claims": [{"id": "C1", "status": "FAIL"}]}
    assert _overall_verdict(failing, INFERRED_CLAIMS) == "INCONSISTENT"

    partial = {"claims": [{"id": "C1", "status": "PARTIAL"}]}
    assert _overall_verdict(partial, INFERRED_CLAIMS) == "NO DESCRIPTION"


def test_stated_claims_keep_the_old_scale():
    stated = [{"id": "C1", "text": "x", "category": "feature", "source": "stated"}]
    assert _overall_verdict({"claims": [{"status": "PASS"}]}, stated) == "ACCURATE"
    assert _overall_verdict({"claims": [{"status": "FAIL"}]}, stated) == "CONTRADICTED"
    assert _overall_verdict({"claims": [{"status": "PASS"}]}) == "ACCURATE"


def test_report_offers_a_suggested_description(tmp_path):
    findings = {"claims": [{"id": "C1", "status": "PASS", "evidence": [], "note": ""}],
                "docs": [], "impact": [], "threads": [], "unresolved_questions": []}
    report = build_report(SNAPSHOT, INFERRED_CLAIMS, findings, [], tmp_path)
    assert "Không có mô tả — đã suy luận 1 yêu cầu từ code" in report
    assert "## Mô tả đề xuất" in report
    assert "- Thử lại thanh toán tối đa 5 lần" in report
    assert "Yêu cầu (suy luận từ code)" in report


def test_comment_offers_a_suggested_description():
    findings = {"claims": [{"id": "C1", "status": "PASS", "evidence": [], "note": ""}],
                "docs": [], "impact": [], "threads": [], "unresolved_questions": []}
    comment = build_comment(SNAPSHOT, INFERRED_CLAIMS, findings, [])
    assert "Mô tả đề xuất" in comment
    assert "Không có mô tả — đã suy luận 1 yêu cầu từ code" in comment
    assert "Thử lại thanh toán tối đa 5 lần" in comment

    stated = build_comment(SNAPSHOT, CLAIMS, FINDINGS, ANSWERS)
    assert "Mô tả đề xuất" not in stated


def test_ping_reports_the_inferred_verdict():
    findings = {"claims": [{"id": "C1", "status": "FAIL"}], "docs": [],
                "impact": [], "threads": [], "unresolved_questions": []}
    ping = build_ping(SNAPSHOT, findings, completed_at="t", claims=INFERRED_CLAIMS)
    assert "Không có mô tả — 1 trong 1 yêu cầu suy luận bị mâu thuẫn" in ping


def test_verdict_label_carries_the_proportion():
    from src.synthesize import verdict_label

    def findings(pass_n=0, fail=0, partial=0):
        return {"claims": [{"status": "PASS"}] * pass_n
                          + [{"status": "FAIL"}] * fail
                          + [{"status": "PARTIAL"}] * partial}

    assert verdict_label("CONTRADICTED", findings(22, 1)) == "1 trong 23 yêu cầu bị mâu thuẫn"
    assert verdict_label("CONTRADICTED", findings(3, 20)) == "20 trong 23 yêu cầu bị mâu thuẫn"
    assert verdict_label("ACCURATE", findings(23)) == "Tất cả 23 yêu cầu đã được xác minh"
    assert verdict_label("PARTIAL", findings(20, 0, 3)) == "3 trong 23 yêu cầu chưa được chứng minh"
    assert verdict_label("NO CLAIMS", findings()) == "Không có yêu cầu nào"


def test_verdict_label_is_singular_for_one_claim():
    from src.synthesize import verdict_label

    one = {"claims": [{"status": "FAIL"}]}
    assert verdict_label("CONTRADICTED", one) == "1 trong 1 yêu cầu bị mâu thuẫn"
    assert verdict_label("ACCURATE", {"claims": [{"status": "PASS"}]}) == "Tất cả 1 yêu cầu đã được xác minh"


def test_report_and_comment_agree_on_the_verdict_text(tmp_path):
    from src.synthesize import _overall_verdict, verdict_label

    findings = {"claims": [{"id": "C1", "status": "PASS", "evidence": [], "note": ""},
                           {"id": "C2", "status": "FAIL", "evidence": [], "note": ""}],
                "docs": [], "impact": [], "threads": [], "unresolved_questions": []}
    claims = [{"id": "C1", "text": "a", "category": "feature", "source": "stated"},
              {"id": "C2", "text": "b", "category": "feature", "source": "stated"}]
    label = verdict_label(_overall_verdict(findings, claims), findings)
    assert label == "1 trong 2 yêu cầu bị mâu thuẫn"
    assert label in build_report(SNAPSHOT, claims, findings, [], tmp_path)
    assert label in build_comment(SNAPSHOT, claims, findings, [])


def test_verdict_label_denominator_survives_a_dead_claims_shard():
    from src.synthesize import verdict_label

    planned = [{"id": f"C{i}", "source": "stated"} for i in range(1, 24)]
    returned = {"claims": [{"id": f"C{i}", "status": "PASS"} for i in range(1, 15)]
                          + [{"id": "C15", "status": "FAIL"}]}
    assert verdict_label("CONTRADICTED", returned, planned) == "1 trong 23 yêu cầu bị mâu thuẫn"
    assert verdict_label("CONTRADICTED", returned) == "1 trong 15 yêu cầu bị mâu thuẫn"


def test_a_dead_claims_shard_can_never_read_as_accurate():
    from src.synthesize import _overall_verdict, verdict_label

    planned = [{"id": f"C{i}", "source": "stated"} for i in range(1, 24)]
    survived = {"claims": [{"id": f"C{i}", "status": "PASS"} for i in range(1, 16)]}

    verdict = _overall_verdict(survived, planned)
    assert verdict == "PARTIAL"
    assert verdict_label(verdict, survived, planned) == "8 trong 23 yêu cầu chưa được chứng minh"

    whole = {"claims": [{"id": f"C{i}", "status": "PASS"} for i in range(1, 24)]}
    assert _overall_verdict(whole, planned) == "ACCURATE"


# --- GitHub-safe readability -------------------------------------------------

MIXED = {
    "claims": [
        {"id": "C1", "status": "PASS", "evidence": ["a.py:1"], "note": "ok"},
        {"id": "C2", "status": "FAIL", "evidence": ["b.py:2", "c.py:3"], "note": "sai"},
        {"id": "C3", "status": "UNVERIFIED", "evidence": [], "note": "?"},
    ],
    "docs": [{"path": "docs/a.md", "status": "MATCH", "what": "khớp"}],
    "impact": [], "threads": [],
    "unresolved_questions": ["Backend có nhận idToken không?"],
}
MIXED_CLAIMS = [
    {"id": "C1", "text": "x", "category": "feature", "source": "stated"},
    {"id": "C2", "text": "y", "category": "bugfix", "source": "stated"},
    {"id": "C3", "text": "z", "category": "chore", "source": "stated"},
]


def test_comment_has_no_inline_style():
    """GitHub xoá mọi thuộc tính style — màu không được mang nghĩa."""
    body = build_comment(SNAPSHOT, MIXED_CLAIMS, MIXED, [])
    assert "style=" not in body
    assert "background-color" not in body


def test_status_is_a_glyph_plus_a_vietnamese_word():
    body = build_comment(SNAPSHOT, MIXED_CLAIMS, MIXED, [])
    assert "🔴 Không khớp" in body
    assert "🟢 Trùng khớp" in body
    assert "⚪ Chưa xác minh" in body


def test_worst_claims_come_first():
    body = build_comment(SNAPSHOT, MIXED_CLAIMS, MIXED, [])
    assert body.index("<td>C2</td>") < body.index("<td>C3</td>") < body.index("<td>C1</td>")


def test_category_is_shown_in_vietnamese():
    body = build_comment(SNAPSHOT, MIXED_CLAIMS, MIXED, [])
    assert "Sửa lỗi" in body and "Bảo trì" in body
    assert "<td>bugfix</td>" not in body


def test_unknown_category_falls_back_to_the_raw_value():
    claims = [{"id": "C1", "text": "x", "category": "weird", "source": "stated"}]
    findings = {"claims": [{"id": "C1", "status": "PASS", "evidence": [], "note": ""}],
                "docs": [], "impact": [], "threads": [], "unresolved_questions": []}
    assert "<td>weird</td>" in build_comment(SNAPSHOT, claims, findings, [])


def test_empty_sections_are_dropped():
    body = build_comment(SNAPSHOT, MIXED_CLAIMS, MIXED, [])
    assert "Luồng bình luận review" not in body
    assert "Nhật ký xác nhận" not in body
    assert "Tác động yêu cầu" not in body


def test_all_match_docs_stay_collapsed_but_wrong_docs_open():
    collapsed = build_comment(SNAPSHOT, MIXED_CLAIMS, MIXED, [])
    assert "<details><summary><b>📄 Tài liệu so với thực tế" in collapsed
    opened = build_comment(SNAPSHOT, CLAIMS, FINDINGS, [])
    assert "<details open><summary><b>📄 Tài liệu so với thực tế" in opened


def test_unresolved_questions_reach_the_comment_until_answered():
    pending = build_comment(SNAPSHOT, MIXED_CLAIMS, MIXED, [])
    assert "Câu hỏi chưa giải quyết" in pending
    assert "Backend có nhận idToken không?" in pending
    answered = build_comment(
        SNAPSHOT, MIXED_CLAIMS, MIXED,
        [{"question": "Backend có nhận idToken không?", "answer": "y"}])
    assert "Câu hỏi chưa giải quyết" not in answered


def test_evidence_paths_are_code_and_cells_are_escaped():
    findings = {"claims": [{"id": "C1", "status": "PASS", "evidence": ["a.py:1"],
                            "note": "<script>alert(1)</script>"}],
                "docs": [], "impact": [], "threads": [], "unresolved_questions": []}
    body = build_comment(SNAPSHOT, CLAIMS, findings, [])
    assert "<code>a.py:1</code>" in body
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_a_status_outside_the_schema_stays_visible_but_in_vietnamese():
    """Agents sometimes put a thread status (FIXED) on an impact row."""
    findings = {"claims": [], "docs": [],
                "impact": [{"requirement": "Hiển thị comment", "impact": "FIXED", "detail": "d"},
                           {"requirement": "Không trạng thái", "detail": "d"}],
                "threads": [], "unresolved_questions": []}
    body = build_comment(SNAPSHOT, [], findings, [])
    assert "Không rõ (FIXED)" in body
    assert "Chưa xác minh" in body
    assert ">FIXED<" not in body


def test_status_label_prefers_the_known_word():
    from src.synthesize import IMPACT_STATUS_LABELS, status_label

    assert status_label("BROKEN", IMPACT_STATUS_LABELS) == "Bị phá vỡ"
    assert status_label("", IMPACT_STATUS_LABELS) == "Chưa xác minh"
    assert status_label(None, IMPACT_STATUS_LABELS) == "Chưa xác minh"
