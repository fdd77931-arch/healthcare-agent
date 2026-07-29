from pathlib import Path
import subprocess


LOGIC_MODULE = Path(__file__).parents[1] / "app" / "web" / "app_logic.js"


def test_browser_logic_enforces_safe_recovery_and_coherent_feedback():
    script = r"""
const assert = require("node:assert/strict");
const logic = require(process.argv[1]);

const active = {
  session_id: "opaque",
  status: "active",
  question: {id: "onset", prompt: "何时开始？", answer_type: "free_text"},
  result: null,
};
const completed = {
  session_id: "opaque",
  status: "completed",
  question: null,
  result: {urgency_level: "routine"},
};

assert.equal(logic.validateSessionPayload(active), active);
assert.equal(logic.validateSessionPayload(completed), completed);
assert.throws(
  () => logic.validateSessionPayload({
    session_id: "opaque",
    status: "completed",
    question: null,
    result: null,
  }),
  /invalid_response/,
);
assert.deepEqual(logic.errorRecovery(422), {kind: "edit"});
assert.deepEqual(logic.errorRecovery(500), {kind: "retry"});
assert.deepEqual(logic.feedbackState(true), {
  label: "helpful",
  reasonRequired: false,
});
assert.deepEqual(logic.feedbackState(false), {
  label: null,
  reasonRequired: true,
});
assert.deepEqual(
  logic.feedbackPayload(true, "unclear_question"),
  {helpful: true, label: "helpful"},
);
assert.deepEqual(
  logic.feedbackPayload(false, "unclear_question"),
  {helpful: false, label: "unclear_question"},
);
assert.equal(logic.clearNotice(null), "本次记录已清除。");
assert.equal(logic.clearNotice({status: 404}), "本次记录已清除。");
assert.match(logic.clearNotice({status: 503}), /本页记录已清除/);
"""

    completed = subprocess.run(
        ["node", "-e", script, str(LOGIC_MODULE)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
