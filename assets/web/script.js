// Ghost Net Landing Page - Interactive Elements
// Minimal JavaScript for enhanced user experience

document.addEventListener('DOMContentLoaded', function() {
    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Add active state to nav links on scroll
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-links a');
    
    window.addEventListener('scroll', () => {
        let current = '';
        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.clientHeight;
            if (window.pageYOffset >= sectionTop - 200) {
                current = section.getAttribute('id');
            }
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${current}`) {
                link.classList.add('active');
            }
        });
    });

    // Animate stats on scroll
    const observerOptions = {
        threshold: 0.5,
        rootMargin: '0px'
    };

    const statsObserver = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate');
            }
        });
    }, observerOptions);

    document.querySelectorAll('.stat').forEach(stat => {
        statsObserver.observe(stat);
    });

    // Animate feature cards on scroll
    const cardsObserver = new IntersectionObserver(function(entries) {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.classList.add('visible');
                }, index * 100);
            }
        });
    }, observerOptions);

    document.querySelectorAll('.feature-card, .use-case, .faq-item').forEach(card => {
        cardsObserver.observe(card);
    });

    // Copy checksum to clipboard
    document.querySelectorAll('.checksum-value').forEach(element => {
        element.style.cursor = 'pointer';
        element.title = 'Click to copy';
        
        element.addEventListener('click', function() {
            const text = this.textContent;
            if (text !== 'Generate APK first') {
                navigator.clipboard.writeText(text).then(() => {
                    const original = this.textContent;
                    this.textContent = '✓ Copied!';
                    setTimeout(() => {
                        this.textContent = original;
                    }, 2000);
                });
            }
        });
    });

    // Add download tracking (optional analytics)
    document.querySelectorAll('a[download]').forEach(link => {
        link.addEventListener('click', function() {
            console.log('Download initiated:', this.getAttribute('href'));
            // Add your analytics tracking here if needed
        });
    });

    // Mobile menu toggle (if needed)
    const createMobileMenu = () => {
        if (window.innerWidth <= 768) {
            const nav = document.querySelector('.nav');
            const navLinks = document.querySelector('.nav-links');
            
            // Create hamburger button if it doesn't exist
            if (!document.querySelector('.menu-toggle')) {
                const menuToggle = document.createElement('button');
                menuToggle.className = 'menu-toggle';
                menuToggle.innerHTML = '☰';
                menuToggle.style.cssText = `
                    background: none;
                    border: none;
                    color: var(--neon-green);
                    font-size: 2rem;
                    cursor: pointer;
                    display: none;
                `;
                
                if (window.innerWidth <= 768) {
                    menuToggle.style.display = 'block';
                }
                
                menuToggle.addEventListener('click', () => {
                    navLinks.classList.toggle('mobile-active');
                });
                
                nav.appendChild(menuToggle);
            }
        }
    };

    createMobileMenu();
    window.addEventListener('resize', createMobileMenu);

    // Add glow effect to buttons on mouse move
    document.querySelectorAll('.btn-primary').forEach(btn => {
        btn.addEventListener('mousemove', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            this.style.setProperty('--mouse-x', `${x}px`);
            this.style.setProperty('--mouse-y', `${y}px`);
        });
    });

    // Console Easter Egg
    console.log('%c👻 Ghost Net', 'font-size: 24px; color: #4CAF50; font-weight: bold;');
    console.log('%cWelcome, curious developer!', 'font-size: 14px; color: #00D9FF;');
    console.log('%cThe network is YOU.', 'font-size: 12px; color: #b0b0b0;');
    console.log('%cCheck out the source: https://github.com/yourusername/ghostnet', 'font-size: 12px; color: #707070;');
});

// Konami Code Easter Egg (optional fun)
let konamiCode = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];
let konamiIndex = 0;

document.addEventListener('keydown', function(e) {
    if (e.key === konamiCode[konamiIndex]) {
        konamiIndex++;
        if (konamiIndex === konamiCode.length) {
            activateMatrixMode();
            konamiIndex = 0;
        }
    } else {
        konamiIndex = 0;
    }
});

function activateMatrixMode() {
    console.log('%c🎉 MATRIX MODE ACTIVATED!', 'font-size: 20px; color: #4CAF50; font-weight: bold;');
    
    // Add matrix rain effect
    const canvas = document.createElement('canvas');
    canvas.style.position = 'fixed';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '9999';
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    document.body.appendChild(canvas);
    
    const ctx = canvas.getContext('2d');
    const chars = '01GHOSTNET👻🔒📡💀';
    const fontSize = 14;
    const columns = canvas.width / fontSize;
    const drops = [];
    
    for (let i = 0; i < columns; i++) {
        drops[i] = 1;
    }
    
    let frameCount = 0;
    const maxFrames = 300; // Run for 5 seconds at 60fps
    
    function drawMatrix() {
        ctx.fillStyle = 'rgba(18, 18, 18, 0.05)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        ctx.fillStyle = '#4CAF50';
        ctx.font = `${fontSize}px monospace`;
        
        for (let i = 0; i < drops.length; i++) {
            const text = chars[Math.floor(Math.random() * chars.length)];
            ctx.fillText(text, i * fontSize, drops[i] * fontSize);
            
            if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                drops[i] = 0;
            }
            drops[i]++;
        }
        
        frameCount++;
        if (frameCount < maxFrames) {
            requestAnimationFrame(drawMatrix);
        } else {
            canvas.remove();
        }
    }
    
    drawMatrix();
}
