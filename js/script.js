// Is line se hum check kar sakte hain ki file load hui ya nahi.
console.log("script.js loaded successfully!");

document.addEventListener('DOMContentLoaded', () => {
    console.log("HTML Document is ready. Running script...");

    // --- Firebase Configuration ---
    // !!! IMPORTANT: YAHAN APNA SAHI FIREBASE CONFIG PASTE KAREIN !!!
    const firebaseConfig = {
        apiKey: "AIzaSy...",
        authDomain: "your-project.firebaseapp.com",
        databaseURL: "https://turnament-c183f-default-rtdb.firebaseio.com",
        projectId: "your-project-id",
        storageBucket: "your-project.appspot.com",
        messagingSenderId: "...",
        appId: "..."
    };

    // Initialize Firebase
    try {
        if (!firebase.apps.length) {
            firebase.initializeApp(firebaseConfig);
            console.log("Firebase Initialized Successfully!");
        }
        const db = firebase.database();
        const auth = firebase.auth();
    } catch (e) {
        console.error("Firebase initialization failed!", e);
        // Agar Firebase hi nahi chala, to aage kuch nahi chalega.
        return; 
    }
    
    // Ab hum har element ko check karke hi use karenge
    
    // --- LOGIC FOR INDEX.HTML ---
    const freeSubmitBtn = document.getElementById('freeSubmit');
    if (freeSubmitBtn) {
        console.log("Found 'Launch Free Test' button on the page.");
        freeSubmitBtn.addEventListener('click', () => {
            alert("Launch Free Test button was clicked!");
            // Yahan aapka API call ka logic aayega
        });
    }

    const paidSubmitBtn = document.getElementById('paidSubmit');
    if (paidSubmitBtn) {
        console.log("Found 'Upgrade to Premium' button on the page.");
        paidSubmitBtn.addEventListener('click', () => {
            const paymentModal = document.getElementById('paymentModal');
            if (paymentModal) {
                paymentModal.classList.add('active');
            }
        });
    }

    const closeModalBtn = document.getElementById('closeModal');
    if(closeModalBtn){
        closeModalBtn.addEventListener('click', () => {
            const paymentModal = document.getElementById('paymentModal');
            if (paymentModal) {
                paymentModal.classList.remove('active');
            }
        });
    }

    // --- LOGIC FOR ADMIN.HTML ---
    const loginBtn = document.getElementById('loginBtn');
    if (loginBtn) {
        console.log("Found 'Secure Login' button on the page.");
        loginBtn.addEventListener('click', () => {
            alert("Login button was clicked!");
            // Yahan aapka login ka logic aayega
        });
    }
    
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) {
        console.log("Found 'Save Configuration' button on the page.");
        saveBtn.addEventListener('click', () => {
            alert("Save button was clicked!");
        });
    }

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        console.log("Found 'Logout' button on the page.");
        logoutBtn.addEventListener('click', () => {
            alert("Logout button was clicked!");
        });
    }
});