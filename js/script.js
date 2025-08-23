// Firebase Configuration
const firebaseConfig = {
    apiKey: "AIzaSyAg6E4_J6q9n0kFWwMo_uq1G8nJlsmDSDA",
    authDomain: "turnament-c183f.firebaseapp.com",
    databaseURL: "https://turnament-c183f-default-rtdb.firebaseio.com",
    projectId: "turnament-c183f",
    storageBucket: "turnament-c183f.appspot.com",
    messagingSenderId: "523966497566",
    appId: "1:523966497566:web:72f37516ecd277da4cff0f"
};

// Initialize Firebase
firebase.initializeApp(firebaseConfig);
const db = firebase.database();
const auth = firebase.auth();

// Global config storage
let config = {};

// Create animated particles
function createParticles() {
    const particles = document.getElementById('particles');
    if (!particles) return;
    
    for (let i = 0; i < 50; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = Math.random() * 100 + '%';
        particle.style.top = Math.random() * 100 + '%';
        particle.style.width = particle.style.height = Math.random() * 4 + 2 + 'px';
        particle.style.animationDelay = Math.random() * 6 + 's';
        particle.style.animationDuration = (Math.random() * 3 + 3) + 's';
        particles.appendChild(particle);
    }
}

// Initialize particles on page load
document.addEventListener('DOMContentLoaded', () => {
    createParticles();
});

// Fetch configuration from Firebase
db.ref('config').on('value', (snapshot) => {
    config = snapshot.val() || {};
    
    // Update footer links if element exists
    const footerLinks = document.getElementById('contactLinks');
    if (footerLinks) {
        footerLinks.innerHTML = `
            <a href="${config.contact || '#'}"><i class="fas fa-envelope"></i> Contact</a>
            <a href="${config.telegram || '#'}"><i class="fab fa-telegram"></i> Telegram</a>
            <a href="${config.youtube || '#'}"><i class="fab fa-youtube"></i> YouTube</a>
            <a href="${config.devContact || '#'}"><i class="fas fa-code"></i> Developer</a>
        `;
    }
    
    // Update QR image and contact link
    const qrImage = document.getElementById('qrImage');
    const contactLink = document.getElementById('contactLink');
    if (qrImage) qrImage.src = config.qrCodeUrl || '';
    if (contactLink) contactLink.href = config.contact || '#';
});

// Enhanced button loading state
function setButtonLoading(button, loading) {
    const btnText = button.querySelector('.btn-text');
    if (!btnText) return;
    
    if (loading) {
        btnText.innerHTML = '<span class="loading"></span>Processing...';
        button.disabled = true;
        button.style.opacity = '0.7';
    } else {
        const originalText = button.id === 'freeSubmit' ? 'Launch Free Test' : 
                            button.id === 'paidUidSubmit' ? 'Process Premium Request' : 
                            'Upgrade to Premium';
        btnText.textContent = originalText;
        button.disabled = false;
        button.style.opacity = '1';
    }
}

// Free Mode Handler
document.addEventListener('DOMContentLoaded', () => {
    const freeSubmitBtn = document.getElementById('freeSubmit');
    if (freeSubmitBtn) {
        freeSubmitBtn.addEventListener('click', async () => {
            const uid = document.getElementById('uidFree').value.trim();
            const errorEl = document.getElementById('freeError');
            const resultEl = document.getElementById('freeResult');
            
            errorEl.style.display = 'none';
            resultEl.style.display = 'none';

            if (!uid) {
                errorEl.textContent = 'Please enter a valid UID to continue.';
                errorEl.style.display = 'block';
                return;
            }

            setButtonLoading(freeSubmitBtn, true);

            try {
                const response = await fetch(`/api/proxy?uid=${encodeURIComponent(uid)}`);
                const data = await response.json();
                
                if (response.ok && data.success) {
                    resultEl.className = 'result success';
                    resultEl.innerHTML = `<strong>✅ Success!</strong><br><pre>${JSON.stringify(data.data, null, 2)}</pre>`;
                } else {
                    throw new Error(data.error || 'Unknown error occurred');
                }
                resultEl.style.display = 'block';
            } catch (error) {
                errorEl.textContent = `❌ Error: ${error.message}`;
                errorEl.style.display = 'block';
            } finally {
                setButtonLoading(freeSubmitBtn, false);
            }
        });
    }
});

// Paid Mode Handlers
document.addEventListener('DOMContentLoaded', () => {
    const paidSubmitBtn = document.getElementById('paidSubmit');
    const paymentModal = document.getElementById('paymentModal');
    const closeModalBtn = document.getElementById('closeModal');
    const continueBtn = document.getElementById('continueAfterPayment');
    const paidUidSubmitBtn = document.getElementById('paidUidSubmit');

    if (paidSubmitBtn) {
        paidSubmitBtn.addEventListener('click', () => {
            paymentModal.classList.add('active');
            // Show continue button after 3 seconds (simulate payment processing)
            setTimeout(() => {
                if (continueBtn) continueBtn.style.display = 'block';
            }, 3000);
        });
    }

    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            paymentModal.classList.remove('active');
        });
    }

    if (continueBtn) {
        continueBtn.addEventListener('click', () => {
            paymentModal.classList.remove('active');
            const uidPaidInput = document.getElementById('uidPaidInput');
            if (uidPaidInput) {
                uidPaidInput.style.display = 'block';
                paidSubmitBtn.style.display = 'none';
            }
        });
    }

    if (paidUidSubmitBtn) {
        paidUidSubmitBtn.addEventListener('click', async () => {
            const uid = document.getElementById('uidPaid').value.trim();
            const errorEl = document.getElementById('paidError');
            const resultEl = document.getElementById('paidResult');
            
            errorEl.style.display = 'none';
            resultEl.style.display = 'none';

            if (!uid) {
                errorEl.textContent = 'Please enter a valid UID to continue.';
                errorEl.style.display = 'block';
                return;
            }

            setButtonLoading(paidUidSubmitBtn, true);

            try {
                const response = await fetch(`/api/proxy?uid=${encodeURIComponent(uid)}`);
                const data = await response.json();
                
                if (response.ok && data.success) {
                    resultEl.className = 'result success';
                    resultEl.innerHTML = `<strong>🎉 Premium Request Processed!</strong><br><pre>${JSON.stringify(data.data, null, 2)}</pre>`;
                } else {
                    throw new Error(data.error || 'Unknown error occurred');
                }
                resultEl.style.display = 'block';
            } catch (error) {
                errorEl.textContent = `❌ Error: ${error.message}`;
                errorEl.style.display = 'block';
            } finally {
                setButtonLoading(paidUidSubmitBtn, false);
            }
        });
    }
});

// Admin Panel JavaScript
document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const loginForm = document.getElementById('loginForm');
    const dashboard = document.getElementById('dashboard');
    const loginBtn = document.getElementById('loginBtn');
    const logoutBtn = document.getElementById('logoutBtn');
    const saveBtn = document.getElementById('saveBtn');
    const loginError = document.getElementById('loginError');
    const saveSuccess = document.getElementById('saveSuccess');
    const saveError = document.getElementById('saveError');
    const userEmail = document.getElementById('userEmail');

    // Check if we're on admin page
    if (!loginForm) return;

    // Auth state change
    auth.onAuthStateChanged(user => {
        if (user) {
            loginForm.style.display = 'none';
            dashboard.style.display = 'block';
            userEmail.textContent = user.email;
            loadConfig();
        } else {
            loginForm.style.display = 'block';
            dashboard.style.display = 'none';
        }
    });

    // Load configuration
    function loadConfig() {
        db.ref('config').once('value').then(snapshot => {
            const config = snapshot.val() || {};
            document.getElementById('apiBaseUrl').value = config.apiBaseUrl || '';
            document.getElementById('apiEndpoint').value = config.apiEndpoint || '';
            document.getElementById('qrCodeUrl').value = config.qrCodeUrl || '';
            document.getElementById('contact').value = config.contact || '';
            document.getElementById('price').value = config.price || '';
            document.getElementById('telegram').value = config.telegram || '';
            document.getElementById('youtube').value = config.youtube || '';
            document.getElementById('devContact').value = config.devContact || '';
        });
    }

    // Login
    if (loginBtn) {
        loginBtn.addEventListener('click', async () => {
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            
            loginError.style.display = 'none';

            if (!email || !password) {
                loginError.textContent = 'Please enter both email and password.';
                loginError.style.display = 'block';
                return;
            }

            setButtonLoading(loginBtn, true);

            try {
                await auth.signInWithEmailAndPassword(email, password);
            } catch (error) {
                // If user doesn't exist, create it
                try {
                    await auth.createUserWithEmailAndPassword(email, password);
                } catch (createError) {
                    loginError.textContent = `❌ ${createError.message}`;
                    loginError.style.display = 'block';
                }
            } finally {
                setButtonLoading(loginBtn, false);
            }
        });
    }

    // Logout
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            auth.signOut();
        });
    }

    // Save configuration
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            const config = {
                apiBaseUrl: document.getElementById('apiBaseUrl').value.trim(),
                apiEndpoint: document.getElementById('apiEndpoint').value.trim(),
                qrCodeUrl: document.getElementById('qrCodeUrl').value.trim(),
                contact: document.getElementById('contact').value.trim(),
                price: document.getElementById('price').value.trim(),
                telegram: document.getElementById('telegram').value.trim(),
                youtube: document.getElementById('youtube').value.trim(),
                devContact: document.getElementById('devContact').value.trim()
            };

            saveSuccess.style.display = 'none';
            saveError.style.display = 'none';

            setButtonLoading(saveBtn, true);

            try {
                await db.ref('config').set(config);
                saveSuccess.style.display = 'block';
                setTimeout(() => {
                    saveSuccess.style.display = 'none';
                }, 5000);
            } catch (error) {
                saveError.textContent = `❌ Error: ${error.message}`;
                saveError.style.display = 'block';
            } finally {
                setButtonLoading(saveBtn, false);
            }
        });
    }
});

// Enhanced keyboard support
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('paymentModal');
        if (modal) modal.classList.remove('active');
    }
    if (e.key === 'Enter' && document.getElementById('loginForm') && document.getElementById('loginForm').style.display !== 'none') {
        const loginBtn = document.getElementById('loginBtn');
        if (loginBtn) loginBtn.click();
    }
});

// Auto-resize inputs
document.addEventListener('DOMContentLoaded', () => {
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"]');
    inputs.forEach(input => {
        input.addEventListener('input', (e) => {
            if (e.target.value.length > 0) {
                e.target.style.transform = 'scale(1.02)';
            } else {
                e.target.style.transform = 'scale(1)';
            }
        });
    });
});
