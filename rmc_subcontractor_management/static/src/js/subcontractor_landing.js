/** @odoo-module **/

// Intersection Observer for fade-in animations
document.addEventListener('DOMContentLoaded', function() {
    // Fade-in animation on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, observerOptions);

    // Observe all fade-in and scale-up elements
    document.querySelectorAll('.fade-in, .scale-up').forEach(el => {
        observer.observe(el);
    });

    // Smooth scroll for anchor links
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

    // Number counter animation
    const animateValue = (element, start, end, duration) => {
        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const value = Math.floor(progress * (end - start) + start);

            if (element.textContent.includes('₹')) {
                element.textContent = '₹' + value + 'L+';
            } else if (element.textContent.includes('%')) {
                element.textContent = value + '%';
            } else if (element.textContent.includes('+')) {
                element.textContent = value + '+';
            } else if (element.textContent.includes('hrs')) {
                element.textContent = value + 'hrs';
            } else {
                element.textContent = value;
            }

            if (progress < 1) {
                window.requestAnimationFrame(step);
            }
        };
        window.requestAnimationFrame(step);
    };

    // Observe stat numbers for counter animation
    const statObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && !entry.target.classList.contains('animated')) {
                entry.target.classList.add('animated');
                const text = entry.target.textContent;
                const match = text.match(/(\d+)/);
                if (match) {
                    const endValue = parseInt(match[1]);
                    animateValue(entry.target, 0, endValue, 2000);
                }
            }
        });
    }, { threshold: 0.5 });

    document.querySelectorAll('.stat-number').forEach(el => {
        statObserver.observe(el);
    });

    // Form validation and enhancement
    const forms = document.querySelectorAll('form[action="/subcontractor/lead"]');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const name = form.querySelector('[name="name"]');
            const mobile = form.querySelector('[name="mobile"]');
            const city = form.querySelector('[name="city"]');

            if (!name.value || !mobile.value || !city.value) {
                e.preventDefault();
                alert('कृपया सभी फील्ड भरें / Please fill all fields');
                return false;
            }

            if (mobile.value.length !== 10) {
                e.preventDefault();
                alert('कृपया 10 अंकों का मोबाइल नंबर डालें / Please enter a valid 10-digit mobile number');
                mobile.focus();
                return false;
            }

            // Show loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Submitting...';
            }
        });
    });

    // Add parallax effect to hero section
    const hero = document.querySelector('.subcontractor-landing .hero');
    if (hero) {
        window.addEventListener('scroll', () => {
            const scrolled = window.pageYOffset;
            const rate = scrolled * 0.5;
            hero.style.transform = `translate3d(0, ${rate}px, 0)`;
        });
    }

    // Card hover effects enhancement
    const cards = document.querySelectorAll('.subcontractor-landing .card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-8px) scale(1.02)';
        });
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });
});
