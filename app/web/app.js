"use strict";

const logic = globalThis.XunjiLogic;
if (!logic) {
  throw new Error("XunjiLogic is required");
}

const flowStateIds = [
  "start-state",
  "followup-state",
  "loading-state",
  "emergency-state",
  "result-state",
  "insufficient-state",
  "error-state",
];

const questionOrder = [
  "main_symptom",
  "onset",
  "severity",
  "associated_symptoms",
  "trend",
  "risk_factors",
];

const messagesPath = "/messages";

const rationaleByQuestion = {
  main_symptom: "明确主要症状和部位，有助于判断下一步需要了解什么。",
  onset: "起始时间和持续时长会影响就医时间建议。",
  severity: "不适程度及其对活动的影响，可能改变行动等级。",
  associated_symptoms: "关键伴随表现可以提示是否需要更快就医。",
  trend: "变化趋势是判断能否继续观察的重要依据。",
  risk_factors: "高风险背景可能降低就医门槛。",
};

const urgencyCopy = {
  urgent: {
    badge: "尽快就医",
    heading: "建议今天尽快就医",
  },
  routine: {
    badge: "近期门诊",
    heading: "建议近期安排门诊",
  },
  self_monitor: {
    badge: "短期观察",
    heading: "目前可短期观察变化",
  },
};

const elements = {
  states: flowStateIds.map((id) => document.getElementById(id)),
  symptomForm: document.getElementById("symptom-form"),
  symptomInput: document.getElementById("symptom-input"),
  answerForm: document.getElementById("answer-form"),
  answerInput: document.getElementById("answer-input"),
  questionHeading: document.getElementById("question-heading"),
  questionProgress: document.getElementById("question-progress"),
  questionRationale: document.getElementById("question-rationale"),
  progressFill: document.getElementById("progress-fill"),
  recordStatus: document.getElementById("record-status"),
  statusLive: document.getElementById("status-live"),
  retryButton: document.getElementById("retry-request"),
  returnToEditButton: document.getElementById("return-to-edit"),
  clearButton: document.getElementById("clear-session"),
  restartButton: document.getElementById("restart-assessment"),
  errorHeading: document.getElementById("error-heading"),
  errorMessage: document.getElementById("error-message"),
  emergencyHeading: document.getElementById("emergency-heading"),
  emergencyDisclaimer: document.getElementById("emergency-disclaimer"),
  resultHeading: document.getElementById("result-heading"),
  resultLevel: document.getElementById("result-level"),
  resultWindow: document.getElementById("result-window"),
  resultDisclaimer: document.getElementById("result-disclaimer"),
  departmentList: document.getElementById("department-list"),
  reasonList: document.getElementById("reason-list"),
  unknownList: document.getElementById("unknown-list"),
  signList: document.getElementById("sign-list"),
  visitSummary: document.getElementById("visit-summary"),
  copyButton: document.getElementById("copy-summary"),
  copyStatus: document.getElementById("copy-status"),
  feedbackForm: document.getElementById("feedback-form"),
  feedbackDetails: document.getElementById("feedback-details"),
  feedbackLabel: document.getElementById("feedback-label"),
  feedbackStatus: document.getElementById("feedback-status"),
  insufficientReason: document.getElementById("insufficient-reason"),
  insufficientDisclaimer: document.getElementById("insufficient-disclaimer"),
  trailSteps: Array.from(document.querySelectorAll("[data-trail-step]")),
};

let sessionId = null;
let pendingRequest = false;
let lastAction = null;
let currentSummary = "";
let editableStateId = "start-state";
let editableInput = elements.symptomInput;

function announce(message) {
  elements.statusLive.textContent = "";
  window.requestAnimationFrame(() => {
    elements.statusLive.textContent = message;
  });
}

function setTrail(stage) {
  const stages = ["start", "followup", "result"];
  const currentIndex = stages.indexOf(stage);

  elements.trailSteps.forEach((step, index) => {
    step.classList.toggle("is-current", index === currentIndex);
    step.classList.toggle("is-complete", index < currentIndex);
  });
}

function showState(stateId, options = {}) {
  elements.states.forEach((state) => {
    state.hidden = state.id !== stateId;
  });

  const stage = options.stage || (
    stateId === "start-state"
      ? "start"
      : stateId === "followup-state" || stateId === "loading-state"
        ? "followup"
        : "result"
  );
  setTrail(stage);

  if (options.focus) {
    window.requestAnimationFrame(() => options.focus.focus());
  }
}

function setPending(isPending) {
  pendingRequest = isPending;
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isPending;
  });
  document.getElementById("assessment").setAttribute("aria-busy", String(isPending));
}

async function apiRequest(path, options) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = new Error(`request_failed_${response.status}`);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function replaceList(list, values, emptyCopy) {
  list.replaceChildren();
  const safeValues = Array.isArray(values) && values.length ? values : [emptyCopy];
  safeValues.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    list.append(item);
  });
}

function buildVisitSummary(result, copy) {
  const departments = result.department.length
    ? result.department.join("、")
    : "请由医疗专业人员进一步判断";
  const signs = result.escalation_signs.length
    ? result.escalation_signs.join("；")
    : "如症状明显加重或出现新的高风险表现，请及时升级行动";

  return [
    "循迹｜就诊参考摘要",
    `行动建议：${copy.heading}`,
    `建议时限：${result.time_window}`,
    `可考虑科室：${departments}`,
    `需要留意：${signs}`,
    result.visit_summary,
    result.disclaimer,
  ].join("\n");
}

function renderQuestion(question) {
  const questionIndex = Math.max(questionOrder.indexOf(question.id), 0);
  const current = Math.min(questionIndex + 1, questionOrder.length);

  elements.questionHeading.textContent = question.prompt;
  elements.questionProgress.textContent = `第 ${current} 个问题，共 ${questionOrder.length} 个`;
  elements.questionRationale.textContent =
    rationaleByQuestion[question.id] || "这项信息有助于判断下一步行动。";
  elements.progressFill.style.inlineSize = `${(current / questionOrder.length) * 100}%`;
  elements.recordStatus.textContent = `正在补充 · ${current}/${questionOrder.length}`;
  showState("followup-state", {
    stage: "followup",
    focus: elements.questionHeading,
  });
  announce(`新问题：${question.prompt}`);
}

function renderEmergency(result) {
  elements.emergencyDisclaimer.textContent = result.disclaimer;
  elements.recordStatus.textContent = "需要立即行动";
  showState("emergency-state", {
    stage: "result",
    focus: elements.emergencyHeading,
  });
  announce("评估完成：请立即呼叫 120。");
}

function renderInsufficient(result) {
  const reasons = result.reasoning_summary.length
    ? result.reasoning_summary.join("；")
    : "当前信息不足或存在冲突。";
  elements.insufficientReason.textContent =
    `${reasons} 请联系医疗专业人员进一步确认，不要只依赖在线信息。`;
  elements.insufficientDisclaimer.textContent = result.disclaimer;
  elements.recordStatus.textContent = "需要人工确认";
  showState("insufficient-state", {
    stage: "result",
    focus: document.getElementById("insufficient-heading"),
  });
  announce("评估结束：当前信息不足，需要医疗专业人员进一步确认。");
}

function renderResult(result) {
  const copy = urgencyCopy[result.urgency_level] || urgencyCopy.routine;

  elements.resultLevel.textContent = copy.badge;
  elements.resultHeading.textContent = copy.heading;
  elements.resultWindow.textContent = result.time_window;
  elements.resultDisclaimer.textContent = result.disclaimer;
  replaceList(elements.departmentList, result.department, "由医疗专业人员进一步判断");
  replaceList(elements.reasonList, result.reasoning_summary, "现有信息支持这一行动建议");
  replaceList(elements.unknownList, result.unknowns, "暂无额外未知项");
  replaceList(
    elements.signList,
    result.escalation_signs,
    "如症状明显加重或出现新的高风险表现，请及时升级行动",
  );

  currentSummary = buildVisitSummary(result, copy);
  elements.visitSummary.textContent = currentSummary;
  elements.copyStatus.textContent = "";
  elements.feedbackStatus.textContent = "";
  elements.recordStatus.textContent = "评估完成";
  showState("result-state", {
    stage: "result",
    focus: elements.resultHeading,
  });
  announce(`评估完成：${copy.heading}。`);
}

function handleSessionResponse(payload) {
  sessionId = payload.session_id;

  if (payload.status === "active" && payload.question) {
    renderQuestion(payload.question);
    return;
  }

  if (!payload.result) {
    throw new Error("invalid_response");
  }

  if (payload.result.urgency_level === "emergency") {
    renderEmergency(payload.result);
  } else if (payload.result.urgency_level === "insufficient") {
    renderInsufficient(payload.result);
  } else {
    renderResult(payload.result);
  }
}

function returnToEditableForm(message = "请修改后重新提交。") {
  const stage = editableStateId === "start-state" ? "start" : "followup";
  elements.recordStatus.textContent = "等待修改";
  showState(editableStateId, {
    stage,
    focus: editableInput,
  });
  announce(message);
}

function showRequestError(error) {
  let message = "网络连接可能不稳定。你填写的内容仍保留在本页，可以直接重试。";
  if (error.status === 404) {
    message = "这次匿名会话已经失效。请清除记录后重新开始评估。";
  } else if (error.message === "invalid_response") {
    message = "返回的信息不完整。请重试；如果仍然失败，请重新开始评估。";
  }

  elements.errorMessage.textContent = message;
  elements.recordStatus.textContent = "发送未成功";
  showState("error-state", {
    stage: sessionId ? "followup" : "start",
    focus: elements.errorHeading,
  });
  announce("信息没有发送成功，可以重试刚才的操作。");
}

async function performSessionRequest(path, message, input) {
  if (pendingRequest) {
    return;
  }

  editableInput = input;
  editableStateId = input === elements.symptomInput
    ? "start-state"
    : "followup-state";
  lastAction = () => performSessionRequest(path, message, input);
  setPending(true);
  elements.recordStatus.textContent = "正在安全核对";
  showState("loading-state", { stage: sessionId ? "followup" : "start" });
  announce("正在整理信息。");

  try {
    const payload = logic.validateSessionPayload(
      await apiRequest(path, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
    );
    handleSessionResponse(payload);
    input.value = "";
    lastAction = null;
  } catch (error) {
    if (logic.errorRecovery(error.status).kind === "edit") {
      returnToEditableForm("填写内容无法处理，请修改后重新提交。");
    } else {
      showRequestError(error);
    }
  } finally {
    setPending(false);
  }
}

function submitSymptom(event) {
  event.preventDefault();
  if (pendingRequest || !elements.symptomForm.reportValidity()) {
    return;
  }
  const message = elements.symptomInput.value.trim();
  if (!message) {
    elements.symptomInput.focus();
    return;
  }
  performSessionRequest("/api/sessions", message, elements.symptomInput);
}

function submitAnswer(event) {
  event.preventDefault();
  if (pendingRequest || !elements.answerForm.reportValidity() || !sessionId) {
    return;
  }
  const message = elements.answerInput.value.trim();
  if (!message) {
    elements.answerInput.focus();
    return;
  }
  performSessionRequest(
    `/api/sessions/${encodeURIComponent(sessionId)}${messagesPath}`,
    message,
    elements.answerInput,
  );
}

async function retryLastAction() {
  if (!pendingRequest && lastAction) {
    await lastAction();
  }
}

async function copySummary() {
  if (!currentSummary) {
    return;
  }

  try {
    await navigator.clipboard.writeText(currentSummary);
    elements.copyStatus.textContent = "摘要已复制。";
    announce("就诊摘要已复制。");
  } catch (_error) {
    elements.copyStatus.textContent =
      "浏览器未允许自动复制，请手动选择上方摘要文字。";
  }
}

async function submitFeedback(event) {
  event.preventDefault();
  if (pendingRequest) {
    return;
  }

  const helpfulInput = elements.feedbackForm.querySelector(
    'input[name="helpful"]:checked',
  );
  const submitButton = elements.feedbackForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  elements.feedbackStatus.textContent = "正在提交…";

  try {
    const helpful = helpfulInput.value === "true";
    await apiRequest("/api/feedback", {
      method: "POST",
      body: JSON.stringify(
        logic.feedbackPayload(helpful, elements.feedbackLabel.value),
      ),
    });
    elements.feedbackStatus.textContent = "反馈已记录，谢谢你帮助改进安全表达。";
    announce("反馈已提交。");
  } catch (_error) {
    elements.feedbackStatus.textContent = "反馈未发送成功，请稍后再试。";
  } finally {
    submitButton.disabled = false;
  }
}

function syncFeedbackDetails() {
  const helpfulInput = elements.feedbackForm.querySelector(
    'input[name="helpful"]:checked',
  );
  const state = logic.feedbackState(helpfulInput.value === "true");
  elements.feedbackDetails.hidden = !state.reasonRequired;
  elements.feedbackLabel.disabled = !state.reasonRequired;
  elements.feedbackLabel.required = state.reasonRequired;
}

function resetLocalSession(notice = "本次记录已清除。") {
  sessionId = null;
  lastAction = null;
  currentSummary = "";
  elements.symptomForm.reset();
  elements.answerForm.reset();
  elements.feedbackForm.reset();
  syncFeedbackDetails();
  elements.copyStatus.textContent = "";
  elements.feedbackStatus.textContent = "";
  elements.recordStatus.textContent = "尚未开始";
  showState("start-state", { stage: "start", focus: elements.symptomInput });
  announce(notice);
}

async function clearSession() {
  if (pendingRequest) {
    return;
  }

  if (!sessionId) {
    resetLocalSession();
    return;
  }

  const targetSession = sessionId;
  lastAction = null;
  setPending(true);
  let deleteError = null;
  try {
    await apiRequest(`/api/sessions/${encodeURIComponent(targetSession)}`, {
      method: "DELETE",
    });
  } catch (error) {
    deleteError = error;
  } finally {
    setPending(false);
    resetLocalSession(logic.clearNotice(deleteError));
  }
}

elements.symptomForm.addEventListener("submit", submitSymptom);
elements.answerForm.addEventListener("submit", submitAnswer);
elements.retryButton.addEventListener("click", retryLastAction);
elements.returnToEditButton.addEventListener("click", () => returnToEditableForm());
elements.copyButton.addEventListener("click", copySummary);
elements.feedbackForm.addEventListener("submit", submitFeedback);
elements.feedbackForm
  .querySelectorAll('input[name="helpful"]')
  .forEach((input) => input.addEventListener("change", syncFeedbackDetails));
elements.clearButton.addEventListener("click", clearSession);
elements.restartButton.addEventListener("click", clearSession);
syncFeedbackDetails();
