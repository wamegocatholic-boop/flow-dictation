import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-app.js";
import { getFirestore, collection, addDoc, getDocs, onSnapshot, query, orderBy, deleteDoc, doc } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-firestore.js";

// Firebase Configuration from user
const firebaseConfig = {
  apiKey: "AIzaSyA8XIFoJwrsgV8AL2FnDua4wFjiYQkO7XE",
  authDomain: "flow-dictation.firebaseapp.com",
  projectId: "flow-dictation",
  storageBucket: "flow-dictation.firebasestorage.app",
  messagingSenderId: "630128999591",
  appId: "1:630128999591:web:2f872bfd1e6638c3146f82"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

// --- Navigation Logic ---
document.querySelectorAll('.nav-links li').forEach(link => {
    link.addEventListener('click', () => {
        // Update active nav
        document.querySelectorAll('.nav-links li').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        
        // Update active view
        const tab = link.getAttribute('data-tab');
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active-view'));
        document.getElementById(`${tab}-view`).classList.add('active-view');
        
        // Resize chart if switching to metrics
        if (tab === 'metrics' && window.wpmChartObj) {
            window.wpmChartObj.resize();
        }
    });
});

// --- Metrics Logic ---
let wpmData = [];
let chartInstance = null;

function initChart() {
    const ctx = document.getElementById('wpmChart').getContext('2d');
    Chart.defaults.color = '#9494a0';
    Chart.defaults.font.family = "'Inter', sans-serif";
    
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Words Per Minute',
                data: [],
                borderColor: '#e24a4a',
                backgroundColor: 'rgba(226, 74, 74, 0.1)',
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#e24a4a',
                pointBorderColor: '#0d0d12',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(30, 30, 38, 0.9)',
                    titleFont: { size: 13, family: "'Inter', sans-serif" },
                    bodyFont: { size: 14, weight: 'bold', family: "'Inter', sans-serif" },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    border: { display: false }
                },
                x: {
                    grid: { display: false },
                    border: { display: false },
                    ticks: { maxTicksLimit: 10 }
                }
            }
        }
    });
    window.wpmChartObj = chartInstance;
}

function updateMetricsUI() {
    let totalWords = 0;
    let totalDuration = 0;
    
    const labels = [];
    const dataPoints = [];
    
    wpmData.forEach((metric, index) => {
        // Fallbacks for data field names in case Android uses different ones
        const words = metric.wordCount || metric.words || 0;
        const dur = metric.durationSeconds || metric.duration || 0;
        
        totalWords += words;
        totalDuration += dur;
        
        labels.push(`Dictation ${index + 1}`);
        const wpmVal = metric.wpm || (dur > 0 ? (words / (dur / 60)) : 0);
        dataPoints.push(Math.round(wpmVal));
    });
    
    document.getElementById('total-words').innerText = totalWords.toLocaleString();
    
    const avgWpm = dataPoints.length > 0 ? Math.round(dataPoints.reduce((a,b)=>a+b,0)/dataPoints.length) : 0;
    document.getElementById('avg-wpm').innerText = avgWpm;
    
    // Estimate time saved (assuming average typing speed is 40 WPM vs dictation)
    const timeTypingHrs = (totalWords / 40) / 60;
    const timeDictatingHrs = totalDuration / 3600;
    const timeSaved = Math.max(0, timeTypingHrs - timeDictatingHrs).toFixed(1);
    document.getElementById('time-saved').innerText = `${timeSaved} hrs`;
    
    if (chartInstance) {
        chartInstance.data.labels = labels;
        chartInstance.data.datasets[0].data = dataPoints;
        chartInstance.update();
    }
}

// Fetch Metrics real-time
const qMetrics = query(collection(db, "metrics"), orderBy("timestamp", "asc"));
onSnapshot(qMetrics, (snapshot) => {
    wpmData = [];
    snapshot.forEach((doc) => {
        wpmData.push({ id: doc.id, ...doc.data() });
    });
    updateMetricsUI();
});

// --- Dictionary Logic ---
const dictForm = document.getElementById('dict-form');
const dictList = document.getElementById('dictionary-list');

dictForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const wordInput = document.getElementById('dict-word');
    const replaceInput = document.getElementById('dict-replacement');
    
    const word = wordInput.value.trim();
    const replacement = replaceInput.value.trim();
    
    if (word && replacement) {
        try {
            await addDoc(collection(db, "dictionary"), {
                word: word,
                replacement: replacement,
                timestamp: new Date()
            });
            wordInput.value = '';
            replaceInput.value = '';
        } catch (e) {
            console.error("Error adding document: ", e);
        }
    }
});

// Fetch Dictionary real-time
const qDict = query(collection(db, "dictionary"), orderBy("timestamp", "desc"));
onSnapshot(qDict, (snapshot) => {
    dictList.innerHTML = '';
    snapshot.forEach((docSnap) => {
        const data = docSnap.data();
        const li = document.createElement('li');
        li.className = 'dict-item';
        li.innerHTML = `
            <div class="dict-item-content">
                <span class="dict-word">${data.word}</span>
                <span class="dict-arrow">→</span>
                <span class="dict-replacement">${data.replacement}</span>
            </div>
            <button class="delete-btn" data-id="${docSnap.id}">×</button>
        `;
        dictList.appendChild(li);
    });
    
    // Add delete listeners
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.target.getAttribute('data-id');
            await deleteDoc(doc(db, "dictionary", id));
        });
    });
});
// --- Omni Commands Logic ---
const omniForm = document.getElementById('omni-form');
const omniList = document.getElementById('omni-list');

omniForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const triggerInput = document.getElementById('omni-trigger');
    const actionInput = document.getElementById('omni-action');
    
    const trigger = triggerInput.value.trim();
    const action = actionInput.value.trim();
    
    if (trigger && action) {
        try {
            await addDoc(collection(db, "omni_commands"), {
                trigger: trigger,
                action: action,
                timestamp: new Date()
            });
            triggerInput.value = '';
            actionInput.value = '';
        } catch (e) {
            console.error("Error adding document: ", e);
        }
    }
});

// Fetch Omni Commands real-time
const qOmni = query(collection(db, "omni_commands"), orderBy("timestamp", "desc"));
onSnapshot(qOmni, (snapshot) => {
    omniList.innerHTML = '';
    snapshot.forEach((docSnap) => {
        const data = docSnap.data();
        const li = document.createElement('li');
        li.className = 'dict-item';
        li.innerHTML = `
            <div class="dict-item-content">
                <span class="dict-word">${data.trigger}</span>
                <span class="dict-arrow">→</span>
                <span class="dict-replacement">${data.action}</span>
            </div>
            <button class="delete-btn omni-delete-btn" data-id="${docSnap.id}">×</button>
        `;
        omniList.appendChild(li);
    });
    
    // Add delete listeners
    document.querySelectorAll('.omni-delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.target.getAttribute('data-id');
            await deleteDoc(doc(db, "omni_commands", id));
        });
    });
});

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initChart();
});
