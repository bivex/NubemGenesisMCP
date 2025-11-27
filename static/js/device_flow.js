/**
 * Device Flow Authorization - Frontend JavaScript
 *
 * Handles user code input, validation, and form submission for device authorization.
 * Implements auto-formatting (XXXX-XXXX), validation, and error handling.
 */

(function() {
    'use strict';

    // DOM elements
    const form = document.getElementById('deviceForm');
    const input = document.getElementById('userCodeInput');
    const submitBtn = document.getElementById('submitBtn');
    const errorMessage = document.getElementById('errorMessage');

    /**
     * Auto-format user code input as XXXX-XXXX
     */
    function autoFormatUserCode(value) {
        // Remove all non-alphanumeric characters
        let cleaned = value.replace(/[^A-Z0-9]/gi, '').toUpperCase();

        // Limit to 8 characters
        cleaned = cleaned.substring(0, 8);

        // Add dash after 4 characters
        if (cleaned.length > 4) {
            return cleaned.substring(0, 4) + '-' + cleaned.substring(4);
        }

        return cleaned;
    }

    /**
     * Validate user code format (XXXX-XXXX)
     */
    function isValidUserCode(value) {
        // Match exactly 8 alphanumeric characters with dash in middle
        const pattern = /^[A-Z0-9]{4}-[A-Z0-9]{4}$/;
        return pattern.test(value);
    }

    /**
     * Show error message
     */
    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.add('visible');
        input.classList.add('error');

        // Remove error styling after animation
        setTimeout(() => {
            input.classList.remove('error');
        }, 500);

        // Auto-hide error after 5 seconds
        setTimeout(() => {
            hideError();
        }, 5000);
    }

    /**
     * Hide error message
     */
    function hideError() {
        errorMessage.classList.remove('visible');
    }

    /**
     * Set loading state
     */
    function setLoading(loading) {
        if (loading) {
            submitBtn.classList.add('loading');
            submitBtn.disabled = true;
            input.disabled = true;
        } else {
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
            input.disabled = false;
        }
    }

    /**
     * Submit user code for verification
     */
    async function submitUserCode(userCode) {
        setLoading(true);
        hideError();

        try {
            const response = await fetch('/auth/device/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    user_code: userCode
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Success - redirect to Google OAuth
                if (data.authorization_url) {
                    window.location.href = data.authorization_url;
                } else {
                    throw new Error('No authorization URL returned');
                }
            } else {
                // Error response
                const errorMsg = data.error_description || data.error || 'Invalid or expired code';
                showError(errorMsg);
                setLoading(false);
            }
        } catch (error) {
            console.error('Error verifying user code:', error);
            showError('Unable to verify code. Please check your internet connection and try again.');
            setLoading(false);
        }
    }

    // ========================================================================
    // Event Listeners
    // ========================================================================

    /**
     * Input event - auto-format as user types
     */
    input.addEventListener('input', function(e) {
        const formatted = autoFormatUserCode(e.target.value);
        e.target.value = formatted;

        // Clear error when user starts typing
        if (errorMessage.classList.contains('visible')) {
            hideError();
        }
    });

    /**
     * Paste event - handle pasted codes
     */
    input.addEventListener('paste', function(e) {
        e.preventDefault();
        const pastedText = (e.clipboardData || window.clipboardData).getData('text');
        const formatted = autoFormatUserCode(pastedText);
        input.value = formatted;

        // Clear error
        hideError();

        // Auto-submit if valid
        if (isValidUserCode(formatted)) {
            setTimeout(() => {
                form.dispatchEvent(new Event('submit'));
            }, 300);
        }
    });

    /**
     * Keypress event - only allow alphanumeric
     */
    input.addEventListener('keypress', function(e) {
        const char = String.fromCharCode(e.which || e.keyCode);
        const isAlphanumeric = /[a-z0-9]/i.test(char);

        if (!isAlphanumeric && e.which !== 13) { // Allow Enter key
            e.preventDefault();
        }
    });

    /**
     * Focus event - select all text for easy replacement
     */
    input.addEventListener('focus', function(e) {
        setTimeout(() => {
            e.target.select();
        }, 0);
    });

    /**
     * Form submit event
     */
    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        const userCode = input.value.trim().toUpperCase();

        // Validate format
        if (!userCode) {
            showError('Please enter the device code');
            input.focus();
            return;
        }

        if (!isValidUserCode(userCode)) {
            showError('Invalid code format. Expected: XXXX-XXXX (8 characters)');
            input.focus();
            return;
        }

        // Submit code
        await submitUserCode(userCode);
    });

    // ========================================================================
    // Initialization
    // ========================================================================

    /**
     * Auto-focus input on page load
     */
    window.addEventListener('DOMContentLoaded', function() {
        // Focus input
        input.focus();

        // If code is pre-filled from URL, validate and format it
        if (input.value) {
            const formatted = autoFormatUserCode(input.value);
            input.value = formatted;

            // Auto-submit if valid
            if (isValidUserCode(formatted)) {
                setTimeout(() => {
                    form.dispatchEvent(new Event('submit'));
                }, 500);
            }
        }
    });

    /**
     * Handle browser back button
     */
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) {
            // Page was restored from cache (back button)
            setLoading(false);
            hideError();
        }
    });

})();
