document.addEventListener('DOMContentLoaded', () => {
    console.log("Page loaded. Script is running.");

    // --- Firebase Configuration ---
    // !!! ATTENTION: YAHAN APNI ASLI FIREBASE PROJECT KI DETAILS DAALEIN !!!
    const firebaseConfig = {
  apiKey: "AIzaSyAg6E4_J6q9n0kFWwMo_uq1G8nJlsmDSDA",
  authDomain: "turnament-c183f.firebaseapp.com",
  databaseURL: "https://turnament-c183f-default-rtdb.firebaseio.com",
  projectId: "turnament-c183f",
  storageBucket: "turnament-c183f.firebasestorage.app",
  messagingSenderId: "523966497566",
  appId: "1:523966497566:web:72f37516ecd277da4cff0f",
  measurementId: "G-EPP0V8N8L4"
};

    // Initialize Firebase
    try {
        if (!firebase.apps.length) {
            firebase.initializeApp(firebaseConfig);
            console.log("Firebase Initialized!");
        }
    } catch (e) {
        console.error("Error initializing Firebase:", e);
        alert("Could not connect to Firebase. Please check your config in script.js.");
        return;
    }
    
    const db = firebase.database();
    const auth = firebase.auth();

    // Particle Animation
    const particlesContainer = document.getElementById('particles');
    if (particlesContainer && particlesContainer.children.length === 0) {
        for (let i = 0; i < 30; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            Object.assign(particle.style, {
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                width: `${Math.random() * 10 + 5}px`,
                height: particle.style.width,
                animationDelay: `${Math.random() * 5}s`
            });
            particlesContainer.appendChild(particle);
        }
    }

    // --- LOGIC FOR INDEX.HTML ---
    const freeSubmitBtn = document.getElementById('freeSubmit');
    if (freeSubmitBtn) {
        const paidSubmitBtn = document.getElementById('paidSubmit');
        const paymentModal = document.getElementById('paymentModal');
        const closeModalBtn = document.getElementById('closeModal');
        const contactLinksContainer = document.getElementById('contactLinks');
        const qrImage = document.getElementById('qrImage');
        const contactLink = document.getElementById('contactLink');
        
        db.ref('config').once('value', snapshot => {
            const config = snapshot.val();
            if (config) {
                if (qrImage) qrImage.src = config.qrCodeUrl || '';
                if (contactLink) contactLink.href = config.contact || '#';
                let linksHTML = '';
                if (config.contact) linksHTML += `<a href="${config.contact}" target="_blank"><i class="fas fa-phone"></i> Contact</a>`;
                if (config.telegram) linksHTML += `<a href="${config.telegram}" target="_blank"><i class="fab fa-telegram"></i> Telegram</a>`;
                if (config.youtube) linksHTML += `<a href="${config.youtube}" target="_blank"><i class="fab fa-youtube"></i> YouTube</a>`;
                if (config.devContact) linksHTML += `<a href="${config.devContact}" target="_blank"><i class="fas fa-code"></i> Developer</a>`;
                if (contactLinksContainer) contactLinksContainer.innerHTML = linksHTML;
            }
        });

        freeSubmitBtn.addEventListener('click', async () => {
            const uidInput = document.getElementById('uidFree');
            const uid = uidInput.value.trim();
            const errorDiv = document.getElementById('freeError');
            const resultDiv = document.getElementById('freeResult');
            const btnText = freeSubmitBtn.querySelector('.btn-text') || freeSubmitBtn;

            if (!uid) {
                errorDiv.textContent = 'Please enter a UID.';
                errorDiv.style.display = 'block';
                return;
            }
            errorDiv.style.display = 'none';
            resultDiv.style.display = 'none';
            freeSubmitBtn.disabled = true;
            btnText.innerHTML = '<span class="loading"></span> Processing...';

            try {
                const response = await fetch(`/api/proxy?uid=${uid}`);
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'API Error');
                
                resultDiv.textContent = JSON.stringify(data.data, null, 2);
                resultDiv.style.display = 'block';
            } catch (error) {
                errorDiv.textContent = error.message;
                errorDiv.style.display = 'block';
            } finally {
                freeSubmitBtn.disabled = false;
                btnText.innerHTML = 'Launch Free Test';
            }
        });

        paidSubmitBtn.addEventListener('click', () => paymentModal && paymentModal.classList.add('active'));
        closeModalBtn.addEventListener('click', () => paymentModal && paymentModal.classList.remove('active'));
    }

    // --- LOGIC FOR ADMIN.HTML ---
    const loginBtn = document.getElementById('loginBtn');
    if (loginBtn) {
        const loginForm = document.getElementById('loginForm');
        const dashboard = document.getElementById('dashboard');
        const saveBtn = document.getElementById('saveBtn');
        const logoutBtn = document.getElementById('logoutBtn');

        auth.onAuthStateChanged(user => {
            if (user) {
                loginForm.style.display = 'none';
                dashboard.style.display = 'block';
                document.getElementById('userEmail').textContent = user.email;
                db.ref('config').once('value', snapshot => {
                    const config = snapshot.val() || {};
                    document.getElementById('apiBaseUrl').value = config.apiBaseUrl || '';
                    document.getElementById('apiEndpoint').value = config.apiEndpoint || '';
                    document.getElementById('qrCodeUrl').value = config.qrCodeUrl || '';
                    document.getElementById('price').value = config.price || '';
                    document.getElementById('contact').value = config.contact || '';
                    document.getElementById('telegram').value = config.telegram || '';
                    document.getElementById('youtube').value = config.youtube || '';
                    document.getElementById('devContact').value = config.devContact || '';
                });
            } else {
                loginForm.style.display = 'block';
                dashboard.style.display = 'none';
            }
        });

        loginBtn.addEventListener('click', () => {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const loginError = document.getElementById('loginError');
            auth.signInWithEmailAndPassword(email, password).catch(error => {
                loginError.textContent = error.message;
                loginError.style.display = 'block';
            });
        });

        logoutBtn.addEventListener('click', () => auth.signOut());

        saveBtn.addEventListener('click', () => {
            const configData = {
                apiBaseUrl: document.getElementById('apiBaseUrl').value,
                apiEndpoint: document.getElementById('apiEndpoint').value,
                qrCodeUrl: document.getElementById('qrCodeUrl').value,
                price: document.getElementById('price').value,
                contact: document.getElementById('contact').value,
                telegram: document.getElementById('telegram').value,
                youtube: document.getElementById('youtube').value,
                devContact: document.getElementById('devContact').value
            };
            const saveSuccess = document.getElementById('saveSuccess');
            const saveError = document.getElementById('saveError');
            db.ref('config').set(configData).then(() => {
                saveSuccess.style.display = 'block';
                setTimeout(() => { saveSuccess.style.display = 'none'; }, 3000);
            }).catch(error => {
                saveError.textContent = error.message;
                saveError.style.display = 'block';
            });
        });
    }
});