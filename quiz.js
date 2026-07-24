/**
 * StudySync AI - Landing Page Controller Module
 * Manages UI interactions, sticky animations, FAQs, analytics counters, and standard form workflows.
 */

document.addEventListener('DOMContentLoaded', () => {
    initStickyHeader();
    initMobileNavigation();
    initFaqAccordion();
    initAnalyticsCounters();
    initContactFormHandler();
    initScrollHighlights();
});

/**
 * Adds smooth glass background styling updates to the sticky header during page scroll.
 */
function initStickyHeader() {
    const header = document.querySelector('.header');
    if (!header) return; // guard: avoid throwing if markup is missing

    const handleScroll = () => {
        if (window.scrollY > 50) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll(); // Trigger initial execution check
}

/**
 * Manages responsive slide-out configurations for mobile displays.
 */
function initMobileNavigation() {
    const toggleButton = document.querySelector('.mobile-menu-toggle');
    const navMenu = document.querySelector('.navbar-links-wrapper');
    const navLinks = document.querySelectorAll('.nav-link');

    if (!toggleButton || !navMenu) return; // guard: avoid throwing if markup is missing

    const toggleMenu = () => {
        const isExpanded = toggleButton.getAttribute('aria-expanded') === 'true';
        toggleButton.setAttribute('aria-expanded', !isExpanded);
        toggleButton.classList.toggle('active');
        navMenu.classList.toggle('active');

        // Prevent background document scrolling while drawer menu is active
        document.body.style.overflow = !isExpanded ? 'hidden' : '';
    };

    toggleButton.addEventListener('click', toggleMenu);

    // Auto-close menu overlay once link is clicked
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (navMenu.classList.contains('active')) {
                toggleMenu();
            }
        });
    });
}

/**
 * Orchestrates keyboard-accessible expand/collapse state changes for FAQ Accordions.
 */
function initFaqAccordion() {
    const faqTriggers = document.querySelectorAll('.faq-trigger');
    if (!faqTriggers.length) return; // guard: nothing to wire up

    faqTriggers.forEach(trigger => {
        trigger.addEventListener('click', () => {
            const faqItem = trigger.closest('.faq-item');
            const panel = trigger.nextElementSibling;
            const isOpened = trigger.getAttribute('aria-expanded') === 'true';

            // Close other currently expanded items
            document.querySelectorAll('.faq-item').forEach(item => {
                if (item !== faqItem && item.classList.contains('active')) {
                    const activeTrigger = item.querySelector('.faq-trigger');
                    const activePanel = activeTrigger.nextElementSibling;
                    activeTrigger.setAttribute('aria-expanded', 'false');
                    item.classList.remove('active');
                    activePanel.style.maxHeight = null;
                }
            });

            // Toggle selected state
            trigger.setAttribute('aria-expanded', !isOpened);
            faqItem.classList.toggle('active');

            if (!isOpened) {
                panel.style.maxHeight = panel.scrollHeight + "px";
            } else {
                panel.style.maxHeight = null;
            }
        });
    });
}

/**
 * Intersection Observer matching callback to dynamically animate static numeric metrics
 * once elements load into standard viewport perspective.
 */
function initAnalyticsCounters() {
    const statNumbers = document.querySelectorAll('.stat-number');
    if (!statNumbers.length) return; // guard: nothing to observe

    const countAnimation = (element) => {
        const targetVal = parseFloat(element.getAttribute('data-target'));
        if (isNaN(targetVal)) return; // guard: bad/missing data-target
        const isDecimal = targetVal % 1 !== 0;
        const animationDuration = 1800; // Complete transitions under 1.8s
        const stepsCount = 60;
        const stepTime = animationDuration / stepsCount;
        let currentStepVal = 0;

        const updateCounter = () => {
            currentStepVal += targetVal / stepsCount;
            if (currentStepVal >= targetVal) {
                element.textContent = isDecimal ? targetVal.toFixed(1) : Math.round(targetVal).toLocaleString();
            } else {
                element.textContent = isDecimal ? currentStepVal.toFixed(1) : Math.round(currentStepVal).toLocaleString();
                setTimeout(updateCounter, stepTime);
            }
        };

        updateCounter();
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                countAnimation(entry.target);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.6 });

    statNumbers.forEach(num => observer.observe(num));
}

/**
 * Handles mock asynchronous requests for contact submittals and triggers feedback indicators.
 */
function initContactFormHandler() {
    const form = document.getElementById('contact-form');
    const successToast = document.getElementById('form-success-toast');

    if (!form) return;

    form.addEventListener('submit', (e) => {
        e.preventDefault();

        // Access form properties (for future backend API integration hooks)
        const name = document.getElementById('contact-name').value;
        const email = document.getElementById('contact-email').value;
        const message = document.getElementById('contact-message').value;

        // Simulate secure async submit requests
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Sending Message...';

        setTimeout(() => {
            // Restore visual layout, display feedback state, and reset values
            submitBtn.disabled = false;
            submitBtn.textContent = 'Send Message';
            form.reset();

            if (successToast) {
                successToast.style.display = 'block';
                successToast.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

                // Clear response banner automatically
                setTimeout(() => {
                    successToast.style.display = 'none';
                }, 6000);
            }
        }, 1200);
    });
}

/**
 * Updates dynamic navbar links on viewports as readers traverse standard layout coordinates.
 */
function initScrollHighlights() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-link');
    if (!sections.length || !navLinks.length) return; // guard: nothing to sync

    const observerOptions = {
        root: null,
        rootMargin: '-30% 0px -60% 0px', // Trigger once sections capture active middle screen focus
        threshold: 0
    };

    const sectionObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const activeId = entry.target.getAttribute('id');
                navLinks.forEach(link => {
                    // FIX: this must be a template literal (backticks), not a bare expression.
                    // The original `#${activeId}` (no backticks) is a JS syntax error that
                    // breaks parsing of the entire file.
                    if (link.getAttribute('href') === `#${activeId}`) {
                        link.classList.add('active');
                    } else {
                        link.classList.remove('active');
                    }
                });
            }
        });
    }, observerOptions);

    sections.forEach(section => sectionObserver.observe(section));
}