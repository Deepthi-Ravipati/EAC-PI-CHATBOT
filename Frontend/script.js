// Point this to your API if it's not localhost:8000
const API_BASE = 'https://pi-chatbot.onrender.com';
let SESSION_ID = null;
let QUESTIONS = [];
let idx = 0;

const consentChk = document.getElementById('consentChk');
const startBtn = document.getElementById('startBtn');
const qPane = document.getElementById('qPane');
const questionText = document.getElementById('questionText');
const likertBtns = document.getElementById('likertBtns');
const freeText = document.getElementById('freeText');
const ftInput = document.getElementById('ftInput');
const submitFree = document.getElementById('submitFree');
const donePane = document.getElementById('done');
const progress = document.getElementById('progress');

consentChk.addEventListener('change', () => {
    startBtn.disabled = !consentChk.checked;
});

startBtn.addEventListener('click', async () => {
    await ensureSession(true);
    await loadQuestions();
    document.getElementById('consentBox').hidden = true;
    qPane.hidden = false;
    renderQ();
});

async function ensureSession(consented) {
    const url = new URL(window.location.href);
    const q = url.searchParams.get('session_id');
    if (q) {
        SESSION_ID = q;
        return;
    }
    const res = await fetch(API_BASE + '/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ consented, research_version: 'feedback-v1', user_agent: navigator.userAgent })
    });
    const data = await res.json();
    SESSION_ID = data.session_id;

    // Put session_id in the URL for easy deep-linking / debugging
    url.searchParams.set('session_id', SESSION_ID);
    history.replaceState(null, '', url.toString());
}

async function loadQuestions() {
    const res = await fetch(API_BASE + '/feedback/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID })
    });
    const data = await res.json();
    QUESTIONS = data.questions || [];
    idx = 0;
}

function renderQ() {
    if (idx >= QUESTIONS.length) {
        qPane.hidden = true;
        donePane.hidden = false;
        return;
    }
    const q = QUESTIONS[idx];
    progress.textContent = `Question ${idx + 1} of ${QUESTIONS.length}`;

    questionText.textContent = q.label;
    likertBtns.innerHTML = '';
    freeText.hidden = true;
    likertBtns.hidden = true;

    if (q.type === 'likert') {
        likertBtns.hidden = false;
        for (let n = q.scale_min; n <= q.scale_max; n++) {
            const b = document.createElement('button');
            b.className = 'likert';
            b.textContent = String(n);
            b.addEventListener('click', async () => {
                await saveAnswer(q.key, n, null);
                idx += 1;
                renderQ();
            });
            likertBtns.appendChild(b);
        }
    } else {
        freeText.hidden = false;
        ftInput.value = '';
        submitFree.onclick = async () => {
            await saveAnswer(q.key, null, ftInput.value.trim());
            idx += 1;
            renderQ();
        };
    }
}

async function saveAnswer(q_key, answer_numeric, answer_text) {
    await fetch(API_BASE + '/feedback/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID, q_key, answer_numeric, answer_text })
    });
}

// Optional: call this from your main app after redirecting back
window.endFeedbackSession = async function () {
    await fetch(API_BASE + '/session/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID })
    });
};
// point to your backend CSV
const CSV_URL = 'https://pi-chatbot.onrender.com/feedback/export.csv';

// when feedback is done, set the link
function showDownloadLink() {
  const link = document.getElementById('downloadCsv');
  if (link) link.href = CSV_URL;
}

// modify your code where you mark "done" to also call this
// e.g., in renderQ(), when idx >= QUESTIONS.length:
qPane.hidden = true;
donePane.hidden = false;
showDownloadLink();
























