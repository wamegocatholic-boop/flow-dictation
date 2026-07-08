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
firebase.initializeApp(firebaseConfig);
const db = firebase.firestore();

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
    
    const baselineWPM = parseInt(document.getElementById('baseline-wpm').value) || 40;
    const timeTypingHrs = (totalWords / baselineWPM) / 60;
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
db.collection("metrics").orderBy("timestamp", "asc").onSnapshot((snapshot) => {
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
            await db.collection("dictionary").add({
                word: word,
                replacement: replacement,
                timestamp: firebase.firestore.FieldValue.serverTimestamp()
            });
            wordInput.value = '';
            replaceInput.value = '';
        } catch (e) {
            console.error("Error adding document: ", e);
        }
    }
});

// Fetch Dictionary real-time
db.collection("dictionary").orderBy("timestamp", "desc").onSnapshot((snapshot) => {
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
            await db.collection("dictionary").doc(id).delete();
        });
    });
});
// --- Omni Commands Logic (Master Items) ---
const omniForm = document.getElementById('omni-form');
const omniLibraryContainer = document.getElementById('omni-library-container');
const subcommandsContainer = document.getElementById('omni-subcommands-container');
const btnAddSubcommand = document.getElementById('btn-add-subcommand');
const btnCancelOmni = document.getElementById('btn-cancel-omni');
const formTitle = document.getElementById('omni-form-title');

let activeOmniItems = []; // Store fetched items

// Function to create a new sub-command row
function createSubcommandRow(trigger = '', action = '') {
    const row = document.createElement('div');
    row.className = 'subcommand-row';
    row.style.display = 'flex';
    row.style.gap = '10px';
    row.style.marginBottom = '10px';
    row.innerHTML = `
        <input type="text" class="sub-trigger" placeholder="Trigger (e.g. Ice)" value="${trigger}" style="flex: 1; padding: 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.2); color: white;">
        <input type="text" class="sub-action" placeholder="Output (e.g. Dispenses properly)" value="${action}" style="flex: 2; padding: 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.2); color: white;">
        <button type="button" class="btn-remove-row" style="background: transparent; border: none; color: #ff4444; font-size: 18px; cursor: pointer; padding: 0 5px;">×</button>
    `;
    
    // Auto-add next row if this one gets filled and is the last one
    row.querySelectorAll('input').forEach(input => {
        input.addEventListener('input', () => {
            if (row === subcommandsContainer.lastElementChild && input.value.trim() !== '') {
                createSubcommandRow();
            }
        });
    });

    row.querySelector('.btn-remove-row').addEventListener('click', () => {
        if (subcommandsContainer.children.length > 1) row.remove();
    });

    subcommandsContainer.appendChild(row);
}

// Initial empty row
createSubcommandRow();

btnAddSubcommand.addEventListener('click', () => createSubcommandRow());

function resetOmniForm() {
    omniForm.reset();
    document.getElementById('omni-item-id').value = '';
    subcommandsContainer.innerHTML = '';
    createSubcommandRow();
    formTitle.innerText = 'Create Master Item';
    btnCancelOmni.style.display = 'none';
    document.getElementById('btn-save-omni').innerText = 'Save Item';
}

btnCancelOmni.addEventListener('click', resetOmniForm);

omniForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const id = document.getElementById('omni-item-id').value;
    const category = document.getElementById('omni-category').value.trim();
    const name = document.getElementById('omni-item-name').value.trim();
    const keywordsStr = document.getElementById('omni-keywords').value.trim();
    const notes = document.getElementById('omni-notes').value.trim();
    
    const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];
    
    const commands = [];
    subcommandsContainer.querySelectorAll('.subcommand-row').forEach(row => {
        const trigger = row.querySelector('.sub-trigger').value.trim();
        const action = row.querySelector('.sub-action').value.trim();
        if (trigger && action) {
            commands.push({ trigger, action });
        }
    });
    
    if (!name || !category) return;
    
    const payload = {
        category,
        name,
        keywords,
        notes,
        commands,
        timestamp: firebase.firestore.FieldValue.serverTimestamp()
    };
    
    try {
        if (id) {
            await db.collection("omni_items").doc(id).update(payload);
        } else {
            await db.collection("omni_items").add(payload);
        }
        resetOmniForm();
    } catch (e) {
        console.error("Error saving omni item: ", e);
    }
});

function renderOmniLibrary() {
    omniLibraryContainer.innerHTML = '';
    
    // Group by category
    const grouped = {};
    activeOmniItems.forEach(item => {
        const cat = item.category || 'Uncategorized';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(item);
    });
    
    // Sort categories alphabetically
    const sortedCategories = Object.keys(grouped).sort();
    
    sortedCategories.forEach(cat => {
        const catGroup = document.createElement('div');
        catGroup.style.marginBottom = '20px';
        
        const catHeader = document.createElement('h4');
        catHeader.innerText = cat;
        catHeader.style.color = 'var(--accent-color)';
        catHeader.style.marginBottom = '10px';
        catHeader.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
        catHeader.style.paddingBottom = '5px';
        catGroup.appendChild(catHeader);
        
        // Sort items alphabetically within category
        grouped[cat].sort((a,b) => a.name.localeCompare(b.name));
        
        grouped[cat].forEach(item => {
            const itemEl = document.createElement('div');
            itemEl.className = 'dict-item';
            itemEl.style.display = 'flex';
            itemEl.style.justifyContent = 'space-between';
            itemEl.style.alignItems = 'center';
            itemEl.style.marginBottom = '8px';
            
            const infoDiv = document.createElement('div');
            infoDiv.innerHTML = `<strong>${item.name}</strong> <span style="font-size:12px; color:#aaa;">(${item.commands.length} cmds)</span>`;
            
            const actionsDiv = document.createElement('div');
            actionsDiv.style.display = 'flex';
            actionsDiv.style.gap = '10px';
            
            const btnEdit = document.createElement('button');
            btnEdit.innerText = 'Edit';
            btnEdit.style.background = 'rgba(255,255,255,0.1)';
            btnEdit.style.color = 'white';
            btnEdit.style.border = 'none';
            btnEdit.style.padding = '5px 10px';
            btnEdit.style.borderRadius = '4px';
            btnEdit.style.cursor = 'pointer';
            btnEdit.onclick = () => {
                document.getElementById('omni-item-id').value = item.id;
                document.getElementById('omni-category').value = item.category;
                document.getElementById('omni-item-name').value = item.name;
                document.getElementById('omni-keywords').value = item.keywords.join(', ');
                document.getElementById('omni-notes').value = item.notes || '';
                
                subcommandsContainer.innerHTML = '';
                item.commands.forEach(cmd => createSubcommandRow(cmd.trigger, cmd.action));
                createSubcommandRow(); // Add empty row at end
                
                formTitle.innerText = `Edit: ${item.name}`;
                document.getElementById('btn-save-omni').innerText = 'Update Item';
                btnCancelOmni.style.display = 'block';
                window.scrollTo({ top: 0, behavior: 'smooth' });
            };
            
            const btnDelete = document.createElement('button');
            btnDelete.innerText = '×';
            btnDelete.className = 'delete-btn';
            btnDelete.onclick = async () => {
                if(confirm(`Delete ${item.name}?`)) {
                    await db.collection("omni_items").doc(item.id).delete();
                }
            };
            
            actionsDiv.appendChild(btnEdit);
            actionsDiv.appendChild(btnDelete);
            
            itemEl.appendChild(infoDiv);
            itemEl.appendChild(actionsDiv);
            catGroup.appendChild(itemEl);
        });
        
        omniLibraryContainer.appendChild(catGroup);
    });
}

// Fetch Omni Items real-time
db.collection("omni_items").orderBy("timestamp", "desc").onSnapshot((snapshot) => {
    activeOmniItems = [];
    snapshot.forEach((docSnap) => {
        activeOmniItems.push({ id: docSnap.id, ...docSnap.data() });
    });
    renderOmniLibrary();
});

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    
    const wpmInput = document.getElementById('baseline-wpm');
    if (localStorage.getItem('baselineWPM')) {
        wpmInput.value = localStorage.getItem('baselineWPM');
    }
    wpmInput.addEventListener('input', () => {
        localStorage.setItem('baselineWPM', wpmInput.value);
        updateMetricsUI();
    });
});
