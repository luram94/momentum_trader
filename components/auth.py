"""
Authentication Module
======================
Supabase authentication for the HQM Momentum Scanner app.
"""

import streamlit as st
from typing import Optional, Dict, Any
from supabase import create_client, Client
import os

from logger import get_logger

logger = get_logger('auth')


def get_supabase_client() -> Optional[Client]:
    """
    Get Supabase client using secrets.

    Returns:
        Supabase client or None if not configured.
    """
    try:
        # Try Streamlit secrets first (for cloud deployment)
        if hasattr(st, 'secrets') and 'SUPABASE_URL' in st.secrets:
            url = st.secrets['SUPABASE_URL']
            key = st.secrets['SUPABASE_KEY']
        else:
            # Fall back to environment variables (for local development)
            url = os.environ.get('SUPABASE_URL')
            key = os.environ.get('SUPABASE_KEY')

        if not url or not key:
            logger.warning("Supabase credentials not configured")
            return None

        return create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


def get_authenticated_client() -> Optional[Client]:
    """
    Get Supabase client with current user's session.

    Returns:
        Authenticated Supabase client or None if not logged in.
    """
    if not is_authenticated():
        return None

    client = get_supabase_client()
    if client and st.session_state.get('access_token'):
        try:
            client.auth.set_session(
                st.session_state.access_token,
                st.session_state.get('refresh_token', '')
            )
        except Exception as e:
            logger.debug(f"Session already set or error: {e}")
    return client


def sign_up(email: str, password: str) -> Dict[str, Any]:
    """
    Sign up a new user.

    Args:
        email: User's email address
        password: User's password

    Returns:
        Dict with 'success' bool and 'error' message if failed.
    """
    client = get_supabase_client()
    if not client:
        return {'success': False, 'error': 'Supabase not configured'}

    try:
        response = client.auth.sign_up({
            'email': email,
            'password': password
        })

        if response.user:
            logger.info(f"User signed up: {email}")
            return {
                'success': True,
                'message': 'Check your email to confirm your account!'
            }
        else:
            return {'success': False, 'error': 'Sign up failed'}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Sign up error: {error_msg}")
        return {'success': False, 'error': error_msg}


def sign_in(email: str, password: str) -> Dict[str, Any]:
    """
    Sign in an existing user.

    Args:
        email: User's email address
        password: User's password

    Returns:
        Dict with 'success' bool and 'error' message if failed.
    """
    client = get_supabase_client()
    if not client:
        return {'success': False, 'error': 'Supabase not configured'}

    try:
        response = client.auth.sign_in_with_password({
            'email': email,
            'password': password
        })

        if response.user and response.session:
            # Store session in Streamlit state
            st.session_state.user_id = response.user.id
            st.session_state.user_email = response.user.email
            st.session_state.is_authenticated = True
            st.session_state.access_token = response.session.access_token
            st.session_state.refresh_token = response.session.refresh_token

            logger.info(f"User signed in: {email}")
            return {'success': True}
        else:
            return {'success': False, 'error': 'Invalid credentials'}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Sign in error: {error_msg}")
        return {'success': False, 'error': error_msg}


def sign_out() -> None:
    """Sign out the current user."""
    client = get_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception as e:
            logger.debug(f"Sign out from Supabase: {e}")

    # Clear session state
    st.session_state.user_id = None
    st.session_state.user_email = None
    st.session_state.is_authenticated = False
    st.session_state.access_token = None
    st.session_state.refresh_token = None

    logger.info("User signed out")


def is_authenticated() -> bool:
    """
    Check if user is authenticated.

    Returns:
        True if user is logged in.
    """
    return st.session_state.get('is_authenticated', False)


def get_current_user_id() -> Optional[str]:
    """
    Get the current user's ID.

    Returns:
        User ID or None if not authenticated.
    """
    if is_authenticated():
        return st.session_state.get('user_id')
    return None


def get_current_user_email() -> Optional[str]:
    """
    Get the current user's email.

    Returns:
        User email or None if not authenticated.
    """
    if is_authenticated():
        return st.session_state.get('user_email')
    return None


def require_auth() -> bool:
    """
    Check authentication and show login prompt if not authenticated.

    Returns:
        True if authenticated, False otherwise.
    """
    if not is_authenticated():
        st.warning("Please log in to access this feature.")
        st.info("Go to the main page to log in or create an account.")
        return False
    return True


def render_auth_ui() -> None:
    """Render the login/signup UI in the sidebar."""
    client = get_supabase_client()

    if not client:
        st.sidebar.warning("Authentication not configured")
        st.sidebar.caption("Add SUPABASE_URL and SUPABASE_KEY to secrets")
        return

    if is_authenticated():
        st.sidebar.success(f"Logged in as {get_current_user_email()}")
        if st.sidebar.button("Logout", use_container_width=True):
            sign_out()
            st.rerun()
    else:
        st.sidebar.subheader("Account")

        tab1, tab2 = st.sidebar.tabs(["Login", "Sign Up"])

        with tab1:
            with st.form("login_form"):
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Login", use_container_width=True)

                if submitted:
                    if email and password:
                        result = sign_in(email, password)
                        if result['success']:
                            st.success("Logged in!")
                            st.rerun()
                        else:
                            st.error(result.get('error', 'Login failed'))
                    else:
                        st.error("Please enter email and password")

        with tab2:
            with st.form("signup_form"):
                email = st.text_input("Email", key="signup_email")
                password = st.text_input("Password", type="password", key="signup_password")
                password_confirm = st.text_input(
                    "Confirm Password",
                    type="password",
                    key="signup_password_confirm"
                )
                submitted = st.form_submit_button("Sign Up", use_container_width=True)

                if submitted:
                    if not email or not password:
                        st.error("Please enter email and password")
                    elif password != password_confirm:
                        st.error("Passwords don't match")
                    elif len(password) < 6:
                        st.error("Password must be at least 6 characters")
                    else:
                        result = sign_up(email, password)
                        if result['success']:
                            st.success(result.get('message', 'Account created!'))
                        else:
                            st.error(result.get('error', 'Sign up failed'))


def render_auth_banner() -> None:
    """Render an authentication banner/dialog on the main page for non-authenticated users."""
    if is_authenticated():
        return

    client = get_supabase_client()
    if not client:
        return

    with st.container(border=True):
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Create a Free Account")
            st.markdown("""
            **Sign up to unlock personal features:**
            - **Watchlist** - Track stocks you're interested in
            - **Portfolio** - Monitor your positions and P&L
            - **Data Sync** - Your data persists across sessions

            *Scanner, Sectors, and Backtest are available without login.*
            """)

        with col2:
            st.markdown("####")  # Spacing
            with st.popover("Login / Sign Up", use_container_width=True):
                tab1, tab2 = st.tabs(["Login", "Sign Up"])

                with tab1:
                    with st.form("login_form_banner"):
                        email = st.text_input("Email", key="login_email_banner")
                        password = st.text_input("Password", type="password", key="login_password_banner")
                        submitted = st.form_submit_button("Login", use_container_width=True)

                        if submitted:
                            if email and password:
                                result = sign_in(email, password)
                                if result['success']:
                                    st.success("Logged in!")
                                    st.rerun()
                                else:
                                    st.error(result.get('error', 'Login failed'))
                            else:
                                st.error("Enter email and password")

                with tab2:
                    with st.form("signup_form_banner"):
                        email = st.text_input("Email", key="signup_email_banner")
                        password = st.text_input("Password", type="password", key="signup_password_banner")
                        password_confirm = st.text_input(
                            "Confirm Password",
                            type="password",
                            key="signup_password_confirm_banner"
                        )
                        submitted = st.form_submit_button("Sign Up", use_container_width=True)

                        if submitted:
                            if not email or not password:
                                st.error("Enter email and password")
                            elif password != password_confirm:
                                st.error("Passwords don't match")
                            elif len(password) < 6:
                                st.error("Min 6 characters")
                            else:
                                result = sign_up(email, password)
                                if result['success']:
                                    st.success("Check your email!")
                                else:
                                    st.error(result.get('error', 'Failed'))
