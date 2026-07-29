(function exposeXunjiLogic(root, factory) {
  const logic = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = logic;
  }
  root.XunjiLogic = logic;
})(typeof globalThis === "object" ? globalThis : this, function createXunjiLogic() {
  "use strict";

  function invalidResponse() {
    return new Error("invalid_response");
  }

  function validateSessionPayload(payload) {
    if (
      !payload
      || typeof payload !== "object"
      || typeof payload.session_id !== "string"
      || !payload.session_id
    ) {
      throw invalidResponse();
    }

    if (
      payload.status === "active"
      && payload.question
      && typeof payload.question === "object"
      && typeof payload.question.id === "string"
      && typeof payload.question.prompt === "string"
    ) {
      return payload;
    }

    if (
      payload.status === "completed"
      && payload.result
      && typeof payload.result === "object"
      && typeof payload.result.urgency_level === "string"
    ) {
      return payload;
    }

    throw invalidResponse();
  }

  function errorRecovery(status) {
    return { kind: status === 422 ? "edit" : "retry" };
  }

  function feedbackState(helpful) {
    return helpful
      ? { label: "helpful", reasonRequired: false }
      : { label: null, reasonRequired: true };
  }

  function feedbackPayload(helpful, selectedLabel) {
    const state = feedbackState(helpful);
    return {
      helpful,
      label: state.label || selectedLabel,
    };
  }

  function clearNotice(error) {
    if (!error || error.status === 404) {
      return "本次记录已清除。";
    }
    return "本页记录已清除；服务器暂时未确认，但你可以重新开始。";
  }

  return Object.freeze({
    clearNotice,
    errorRecovery,
    feedbackPayload,
    feedbackState,
    validateSessionPayload,
  });
});
