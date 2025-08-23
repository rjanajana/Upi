document.addEventListener('DOMContentLoaded', () => {

    // --- Firebase Configuration ---
    // IMPORTANT: Fill in your actual Firebase config details here
    const firebaseConfig = {
        apiKey: "YOUR_API_KEY",
        authDomain: "YOUR_AUTH_DOMAIN",
        databaseURL: "https://turnament-c183f-default-rtdb.firebaseio.com",
        projectId: "YOUR_PROJECT_ID",
        storageBucket: "YOUR_STORAGE_BUCKET",
        messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
        appId: "YOUR_APP_ID"
    };

    // Initialize Firebase
    if (!firebase.apps.length) {
        firebase.initializeApp(firebaseConfig);
    }
    const db = firebase.database();
    const auth = firebase.auth();

    // --- Particle Animation (Common to both pages) ---
    const particlesContainer = document.getElementById('particles');
    if (particlesContainer) {
        for (let i = 0; i < 30; i++) {
            let particle = document.createElement('div');
            particle.classList.add('particle');
            particle.style.left = `${Math.random() * 100}%`;
            particle.style.top = `${Math.random() * 100}%`;
            const size = Math.random() * 15 + 5;
            particle.style.width = `${size}px`;
            particle.style.height = `${size}px`;
            particle.style.animationDelay = `${Math.random() * 6}s`;
            particlesContainer.appendChild(particle);
        }
    }

    // --- LOGIC FOR INDEX.HTML ---
    const freeSubmitBtn = document.getElementById('freeSubmit');
    const paidSubmitBtn = document.getElementById('paidSubmit');
    const paymentModal = document.getElementById('paymentModal');
    const closeModalBtn = document.getElementById('closeModal');
    const contactLinksContainer = document.getElementById('contactLinks');
    const qrImage = document.getElementById('qrImage');
    const contactLink = document.getElementById('contactLink');
    
    // Fetch config for index page
    if (contactLinksContainer) {
        db.ref('config').once('value', (snapshot) => {
            const config = snapshot.val();
            if (config) {
                // Set QR code and contact link in modal
                if(qrImage) qrImage.src = config.qrCodeUrl || '';
                if(contactLink) contactLink.href = config.contact || '#';

                // Populate footer links
                let linksHTML = '';
                if(config.contact) linksHTML += `<a href="${config.contact}" target="_blank"><i class="fas fa-phone"></i> Contact</a>`;
                if(config.telegram) linksHTML += `<a href="${config.telegram}" target="_blank"><i class="fab fa-telegram"></i> Telegram</a>`;
                if(config.youtube) linksHTML += `<a href="${config.youtube}" target="_blank"><i class="fab fa-youtube"></i> YouTube</a>`;
                if(config.devContact) linksHTML += `<a href="${config.devContact}" target="_blank"><i class="fas fa-code"></i> Developer</a>`;
                contactLinksContainer.innerHTML = linksHTML;
            }
        });
    }

    if (freeSubmitBtn) {
        freeSubmitBtn.addEventListener('click', async () => {
            const uidInput = document.getElementById('uidFree');
            const uid = uidInput.value.trim();
            const errorDiv = document.getElementById('freeError');
            const resultDiv = document.getElementById('freeResult');
            const btnText = freeSubmitBtn.querySelector('.btn-text');

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

                if (response.ok && data.success) {
                    resultDiv.textContent = JSON.stringify(data.data, null, 2);
                    resultDiv.style.display = 'block';
                } else {
                    errorDiv.textContent = data.error || 'An unknown error occurred.';
                    errorDiv.style.display = 'block';
                }
            } catch (error) {
                errorDiv.textContent = 'Failed to fetch data. Check your connection.';
                errorDiv.style.display = 'block';
            } finally {
                freeSubmitBtn.disabled = false;
                btnText.innerHTML = 'Launch Free Test';
            }
        });
    }

    if (paidSubmitBtn) {
        paidSubmitBtn.addEventListener('click', () => {
            if(paymentModal) paymentModal.classList.add('active');
        });
    }
    
    if(closeModalBtn){
        closeModalBtn.addEventListener('click', () => {
            if(paymentModal) paymentModal.classList.remove('active');
        });
    }

    // --- LOGIC FOR ADMIN.HTML ---
    const loginBtn = document.getElementById('loginBtn');
    const saveBtn = document.getElementById('saveBtn');
    const logoutBtn = document.getElementById('logoutBtn');
    const loginForm = document.getElementById('loginForm');
    const dashboard = document.getElementById('dashboard');

    // Check auth state
    auth.onAuthStateChanged(user => {
        if (user) {
            // User is signed in.
            if(loginForm) loginForm.style.display = 'none';
            if(dashboard) dashboard.style.display = 'block';
            
            const userEmailP = document.getElementById('userEmail');
            if(userEmailP) userEmailP.textContent = user.email;

            // Load config into form
            db.ref('config').once('value', (snapshot) => {
                const config = snapshot.val();
                if(config){
                    document.getElementById('apiBaseUrl').value = config.apiBaseUrl || '';
                    document.getElementById('apiEndpoint').value = config.apiEndpoint || '';
                    document.getElementById('qrCodeUrl').value = config.qrCodeUrl || '';
                    document.getElementById('price').value = config.price || '';
                    document.getElementById('contact').value = config.contact || '';
                    document.getElementById('telegram').value = config.telegram || '';
                    document.getElementById('youtube').value = config.youtube || '';
                    document.getElementById('devContact').value = config.devContact || '';
                }
            });

        } else {
            // User is signed out.
            if(loginForm) loginForm.style.display = 'block';
            if(dashboard) dashboard.style.display = 'none';
        }
    });

    if (loginBtn) {
        loginBtn.addEventListener('click', () => {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const loginError = document.getElementById('loginError');

            auth.signInWithEmailAndPassword(email, password)
                .catch(error => {
                    if(loginError) {
                        loginError.textContent = error.message;
                        loginError.style.display = 'block';
                    }
                });
        });
    }

    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            auth.signOut();
        });
    }

    if (saveBtn) {
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

            db.ref('config').set(configData)
                .then(() => {
                    if(saveSuccess) {
                        saveSuccess.style.display = 'block';
                        setTimeout(() => { saveSuccess.style.display = 'none'; }, 3000);
                    }
                })
                .catch(error => {
                    if(saveError){
                         saveError.textContent = error.message;
                         saveError.style.display = 'block';
                    }
                });
        });
    }
});