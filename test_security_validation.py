#!/usr/bin/env python3
"""
Comprehensive Security Validation Test Suite for Ordinaut.

This test suite validates JWT authentication, authorization, input sanitization,
rate limiting, and security middleware according to production security standards.
"""

import os
import json
import uuid
import time
import asyncio
import requests
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Test configuration
TEST_API_BASE = os.getenv("TEST_API_BASE", "http://localhost:8080")
TEST_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://orchestrator:password@localhost:5432/orchestrator")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")

class SecurityTestResult:
    """Container for security test results."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.vulnerabilities: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        
    def add_pass(self, test_name: str):
        """Record a passing test."""
        self.passed += 1
        print(f"✅ {test_name}")
        
    def add_fail(self, test_name: str, details: str, severity: str = "high"):
        """Record a failing test as vulnerability."""
        self.failed += 1
        vulnerability = {
            "test": test_name,
            "severity": severity,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.vulnerabilities.append(vulnerability)
        print(f"❌ {test_name}: {details}")
        
    def add_warning(self, message: str):
        """Add a warning message."""
        self.warnings.append(message)
        print(f"⚠️  {message}")
        
    def print_summary(self):
        """Print comprehensive security validation summary."""
        total_tests = self.passed + self.failed
        
        print("\n" + "="*80)
        print("SECURITY VALIDATION SUMMARY")
        print("="*80)
        
        print(f"Total Tests Run: {total_tests}")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        
        if self.vulnerabilities:
            print(f"\n🚨 CRITICAL VULNERABILITIES FOUND: {len(self.vulnerabilities)}")
            for vuln in self.vulnerabilities:
                print(f"  - {vuln['severity'].upper()}: {vuln['test']} - {vuln['details']}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        # Production readiness assessment
        print(f"\n📊 PRODUCTION READINESS ASSESSMENT:")
        if self.failed == 0:
            print("🟢 SECURE: No vulnerabilities detected - suitable for production")
        elif len([v for v in self.vulnerabilities if v["severity"] == "critical"]) > 0:
            print("🔴 CRITICAL: Critical vulnerabilities found - DO NOT deploy to production")
        elif len([v for v in self.vulnerabilities if v["severity"] == "high"]) > 0:
            print("🟡 CAUTION: High-severity vulnerabilities - fix before production")
        else:
            print("🟡 REVIEW: Minor security issues - review and address")
            
        print("="*80)


class SecurityValidator:
    """Comprehensive security validation suite."""
    
    def __init__(self, api_base: str, db_url: str):
        self.api_base = api_base
        self.db_url = db_url
        self.results = SecurityTestResult()
        self.session = requests.Session()
        
        # Setup database connection for direct testing
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
    def create_test_agent(self, name: str, scopes: List[str]) -> Dict[str, Any]:
        """Create a test agent directly in database."""
        db = self.SessionLocal()
        try:
            agent_id = str(uuid.uuid4())
            
            # Insert agent directly
            db.execute(text("""
                INSERT INTO agent (id, name, scopes, created_at)
                VALUES (:id, :name, :scopes, :created_at)
            """), {
                "id": agent_id,
                "name": name,
                "scopes": scopes,
                "created_at": datetime.now(timezone.utc)
            })
            db.commit()
            
            return {"id": agent_id, "name": name, "scopes": scopes}
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def generate_jwt_token(self, agent_id: str, scopes: List[str], 
                          expired: bool = False, invalid_signature: bool = False) -> str:
        """Generate JWT token for testing."""
        payload = {
            "sub": agent_id,
            "type": "access",
            "scopes": scopes,
            "name": f"test-agent-{agent_id[:8]}",
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4())
        }
        
        if expired:
            payload["exp"] = datetime.now(timezone.utc) - timedelta(hours=1)
        else:
            payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=1)
        
        secret = "wrong-secret" if invalid_signature else JWT_SECRET_KEY
        return pyjwt.encode(payload, secret, algorithm="HS256")
    
    def test_health_endpoint_accessibility(self):
        """Test that health endpoints don't require authentication."""
        try:
            # Test public health endpoints
            health_endpoints = ["/health", "/health/ready", "/health/live", "/metrics"]
            
            for endpoint in health_endpoints:
                response = self.session.get(f"{self.api_base}{endpoint}")
                if response.status_code == 200:
                    self.results.add_pass(f"Health endpoint {endpoint} accessible")
                else:
                    self.results.add_fail(
                        f"Health endpoint {endpoint} not accessible",
                        f"Expected 200, got {response.status_code}",
                        severity="medium"
                    )
        except Exception as e:
            self.results.add_fail("Health endpoint test", f"Connection error: {str(e)}")
    
    def test_jwt_authentication_flow(self):
        """Test complete JWT authentication flow."""
        try:
            # Create test agent
            agent = self.create_test_agent("jwt-test-agent", ["tasks.read", "tasks.write"])
            
            # Test authentication endpoint
            auth_data = {
                "agent_id": agent["id"],
                "agent_secret": None  # Current implementation doesn't validate secrets
            }
            
            auth_response = self.session.post(
                f"{self.api_base}/agents/auth/token", 
                json=auth_data
            )
            
            if auth_response.status_code == 200:
                tokens = auth_response.json()
                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")
                
                if access_token and refresh_token:
                    self.results.add_pass("JWT token generation successful")
                    
                    # Test using access token
                    headers = {"Authorization": f"Bearer {access_token}"}
                    protected_response = self.session.get(
                        f"{self.api_base}/agents", 
                        headers=headers
                    )
                    
                    if protected_response.status_code == 403:
                        self.results.add_pass("JWT access token validation working")
                    else:
                        self.results.add_fail(
                            "JWT access token validation",
                            f"Expected 403 (no admin scope), got {protected_response.status_code}"
                        )
                        
                    # Test refresh token
                    refresh_data = {"refresh_token": refresh_token}
                    refresh_response = self.session.post(
                        f"{self.api_base}/agents/auth/refresh",
                        json=refresh_data
                    )
                    
                    if refresh_response.status_code == 200:
                        self.results.add_pass("JWT token refresh working")
                    else:
                        self.results.add_fail(
                            "JWT token refresh",
                            f"Expected 200, got {refresh_response.status_code}"
                        )
                else:
                    self.results.add_fail("JWT token generation", "Missing tokens in response")
            else:
                self.results.add_fail(
                    "JWT authentication endpoint",
                    f"Expected 200, got {auth_response.status_code}"
                )
                
        except Exception as e:
            self.results.add_fail("JWT authentication flow", f"Exception: {str(e)}")
    
    def test_token_validation_security(self):
        """Test JWT token validation security."""
        try:
            # Create test agent
            agent = self.create_test_agent("token-security-agent", ["tasks.read"])
            
            # Test expired token
            expired_token = self.generate_jwt_token(agent["id"], agent["scopes"], expired=True)
            headers = {"Authorization": f"Bearer {expired_token}"}
            
            response = self.session.get(f"{self.api_base}/agents", headers=headers)
            if response.status_code == 401:
                self.results.add_pass("Expired token rejection working")
            else:
                self.results.add_fail(
                    "Expired token validation",
                    f"Expected 401, got {response.status_code}",
                    severity="critical"
                )
            
            # Test invalid signature
            invalid_token = self.generate_jwt_token(agent["id"], agent["scopes"], invalid_signature=True)
            headers = {"Authorization": f"Bearer {invalid_token}"}
            
            response = self.session.get(f"{self.api_base}/agents", headers=headers)
            if response.status_code == 401:
                self.results.add_pass("Invalid signature rejection working")
            else:
                self.results.add_fail(
                    "Invalid signature validation",
                    f"Expected 401, got {response.status_code}",
                    severity="critical"
                )
            
            # Test malformed token
            headers = {"Authorization": "Bearer not-a-jwt-token"}
            response = self.session.get(f"{self.api_base}/agents", headers=headers)
            if response.status_code == 401:
                self.results.add_pass("Malformed token rejection working")
            else:
                self.results.add_fail(
                    "Malformed token validation",
                    f"Expected 401, got {response.status_code}",
                    severity="high"
                )
                
        except Exception as e:
            self.results.add_fail("Token validation security", f"Exception: {str(e)}")
    
    def test_scope_based_authorization(self):
        """Test scope-based authorization enforcement."""
        try:
            # Create agents with different scopes
            limited_agent = self.create_test_agent("limited-agent", ["tasks.read"])
            admin_agent = self.create_test_agent("admin-agent", ["admin", "tasks.read", "tasks.write"])
            
            # Test limited agent access to admin endpoint
            limited_token = self.generate_jwt_token(limited_agent["id"], limited_agent["scopes"])
            headers = {"Authorization": f"Bearer {limited_token}"}
            
            response = self.session.get(f"{self.api_base}/agents", headers=headers)
            if response.status_code == 403:
                self.results.add_pass("Scope-based authorization blocking unauthorized access")
            else:
                self.results.add_fail(
                    "Scope-based authorization",
                    f"Limited agent should be blocked, got {response.status_code}",
                    severity="critical"
                )
            
            # Test admin agent access
            admin_token = self.generate_jwt_token(admin_agent["id"], admin_agent["scopes"])
            headers = {"Authorization": f"Bearer {admin_token}"}
            
            response = self.session.get(f"{self.api_base}/agents", headers=headers)
            if response.status_code == 200:
                self.results.add_pass("Scope-based authorization allowing authorized access")
            else:
                self.results.add_fail(
                    "Scope-based authorization",
                    f"Admin agent should be allowed, got {response.status_code}",
                    severity="high"
                )
                
        except Exception as e:
            self.results.add_fail("Scope-based authorization", f"Exception: {str(e)}")
    
    def test_input_validation_and_sanitization(self):
        """Test input validation and sanitization."""
        try:
            # Create admin agent for testing
            admin_agent = self.create_test_agent("input-test-admin", ["admin"])
            admin_token = self.generate_jwt_token(admin_agent["id"], admin_agent["scopes"])
            headers = {"Authorization": f"Bearer {admin_token}"}
            
            # Test SQL injection attempts
            sql_injection_payloads = [
                "'; DROP TABLE agent; --",
                "' OR 1=1 --",
                "'; UPDATE agent SET scopes = '{{admin}}'; --",
                "robert'; DROP TABLE students; --"
            ]
            
            for payload in sql_injection_payloads:
                agent_data = {
                    "name": payload,
                    "scopes": ["test"]
                }
                
                response = self.session.post(
                    f"{self.api_base}/agents",
                    json=agent_data,
                    headers=headers
                )
                
                # Should either reject the input or sanitize it safely
                if response.status_code in [400, 422]:  # Validation error
                    self.results.add_pass(f"SQL injection payload rejected: {payload[:20]}...")
                elif response.status_code == 201:
                    # Check if agent name was sanitized
                    created_agent = response.json()
                    if created_agent["name"] != payload:
                        self.results.add_pass(f"SQL injection payload sanitized: {payload[:20]}...")
                    else:
                        self.results.add_fail(
                            "SQL injection protection",
                            f"Dangerous payload accepted unchanged: {payload}",
                            severity="critical"
                        )
            
            # Test XSS attempts
            xss_payloads = [
                "<script>alert('xss')</script>",
                "javascript:alert('xss')",
                "<img src=x onerror=alert('xss')>",
                "';alert('xss');//"
            ]
            
            for payload in xss_payloads:
                agent_data = {
                    "name": f"xss-test-{payload}",
                    "scopes": ["test"]
                }
                
                response = self.session.post(
                    f"{self.api_base}/agents",
                    json=agent_data,
                    headers=headers
                )
                
                if response.status_code in [400, 422]:
                    self.results.add_pass(f"XSS payload rejected: {payload[:20]}...")
                elif response.status_code == 201:
                    # Check response doesn't contain unescaped payload
                    response_text = response.text
                    if payload in response_text and "<script>" in response_text:
                        self.results.add_fail(
                            "XSS protection",
                            f"XSS payload reflected in response: {payload}",
                            severity="high"
                        )
                    else:
                        self.results.add_pass(f"XSS payload handled safely: {payload[:20]}...")
                        
        except Exception as e:
            self.results.add_fail("Input validation and sanitization", f"Exception: {str(e)}")
    
    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        try:
            # Make rapid requests to test rate limiting
            rate_limit_exceeded = False
            
            for i in range(70):  # Exceed the 60/minute limit
                response = self.session.get(f"{self.api_base}/health")
                
                if response.status_code == 429:  # Too Many Requests
                    rate_limit_exceeded = True
                    self.results.add_pass("Rate limiting is active and enforced")
                    break
                    
                time.sleep(0.1)  # Small delay to avoid overwhelming
            
            if not rate_limit_exceeded:
                self.results.add_warning("Rate limiting not triggered during test - may need Redis or higher load")
                
        except Exception as e:
            self.results.add_fail("Rate limiting test", f"Exception: {str(e)}")
    
    def test_security_headers(self):
        """Test security headers in responses."""
        try:
            response = self.session.get(f"{self.api_base}/health")
            headers = response.headers
            
            # Check for critical security headers
            security_headers = {
                "X-XSS-Protection": "XSS protection header",
                "X-Content-Type-Options": "Content type options header", 
                "X-Frame-Options": "Frame options header",
                "Strict-Transport-Security": "HSTS header",
                "Content-Security-Policy": "CSP header"
            }
            
            for header, description in security_headers.items():
                if header in headers:
                    self.results.add_pass(f"Security header present: {header}")
                else:
                    self.results.add_fail(
                        f"Missing security header: {header}",
                        f"Missing {description} - reduces security posture",
                        severity="medium"
                    )
            
            # Check Server header doesn't reveal sensitive information
            server_header = headers.get("Server", "")
            if server_header and "uvicorn" in server_header.lower():
                self.results.add_warning("Server header reveals implementation details")
            elif server_header:
                self.results.add_pass("Server header appropriately configured")
                
        except Exception as e:
            self.results.add_fail("Security headers test", f"Exception: {str(e)}")
    
    def test_error_information_disclosure(self):
        """Test that error messages don't leak sensitive information."""
        try:
            # Test 404 error doesn't reveal system information
            response = self.session.get(f"{self.api_base}/nonexistent-endpoint")
            
            if response.status_code == 404:
                error_content = response.text.lower()
                
                # Check for information disclosure
                sensitive_info = ["traceback", "stack trace", "file path", "database", "postgresql", "redis"]
                leaked_info = [info for info in sensitive_info if info in error_content]
                
                if leaked_info:
                    self.results.add_fail(
                        "Error information disclosure",
                        f"404 error reveals sensitive information: {', '.join(leaked_info)}",
                        severity="medium"
                    )
                else:
                    self.results.add_pass("404 errors don't leak sensitive information")
            
            # Test 500 error handling (try to trigger)
            admin_agent = self.create_test_agent("error-test-admin", ["admin"])
            admin_token = self.generate_jwt_token(admin_agent["id"], admin_agent["scopes"])
            headers = {"Authorization": f"Bearer {admin_token}"}
            
            # Try to create agent with invalid data to trigger 500
            invalid_data = {"name": None, "scopes": "not-a-list"}
            response = self.session.post(
                f"{self.api_base}/agents",
                json=invalid_data,
                headers=headers
            )
            
            if response.status_code == 500:
                error_content = response.text.lower()
                sensitive_info = ["traceback", "stack trace", "file path", "sqlalchemy", "exception"]
                leaked_info = [info for info in sensitive_info if info in error_content]
                
                if leaked_info:
                    self.results.add_fail(
                        "Error information disclosure",
                        f"500 error reveals sensitive information: {', '.join(leaked_info)}",
                        severity="high"
                    )
                else:
                    self.results.add_pass("500 errors don't leak sensitive information")
                    
        except Exception as e:
            self.results.add_fail("Error information disclosure test", f"Exception: {str(e)}")
    
    def test_audit_logging(self):
        """Test that security events are properly logged."""
        try:
            # Create admin agent for audit testing
            admin_agent = self.create_test_agent("audit-test-admin", ["admin"])
            admin_token = self.generate_jwt_token(admin_agent["id"], admin_agent["scopes"])
            headers = {"Authorization": f"Bearer {admin_token}"}
            
            # Perform action that should be audited
            agent_data = {
                "name": f"audit-test-agent-{uuid.uuid4().hex[:8]}",
                "scopes": ["test"]
            }
            
            response = self.session.post(
                f"{self.api_base}/agents",
                json=agent_data,
                headers=headers
            )
            
            if response.status_code == 201:
                created_agent = response.json()
                
                # Check if audit log was created
                db = self.SessionLocal()
                try:
                    audit_result = db.execute(text("""
                        SELECT action, details FROM audit_log 
                        WHERE actor_agent_id = :agent_id 
                        AND action = 'agent.created'
                        AND subject_id = :subject_id
                        ORDER BY at DESC LIMIT 1
                    """), {
                        "agent_id": admin_agent["id"],
                        "subject_id": created_agent["id"]
                    }).fetchone()
                    
                    if audit_result:
                        self.results.add_pass("Audit logging working - agent creation logged")
                        
                        # Check if sensitive details are excluded from logs
                        details = json.loads(audit_result.details) if audit_result.details else {}
                        if "password" not in str(details).lower() and "secret" not in str(details).lower():
                            self.results.add_pass("Audit logs don't contain sensitive information")
                        else:
                            self.results.add_fail(
                                "Audit log security",
                                "Audit logs may contain sensitive information",
                                severity="medium"
                            )
                    else:
                        self.results.add_fail(
                            "Audit logging",
                            "Agent creation not logged in audit trail",
                            severity="high"
                        )
                        
                finally:
                    db.close()
            else:
                self.results.add_warning("Could not create agent to test audit logging")
                
        except Exception as e:
            self.results.add_fail("Audit logging test", f"Exception: {str(e)}")
    
    def test_authentication_bypass_attempts(self):
        """Test various authentication bypass attempts."""
        try:
            # Test missing authorization header
            response = self.session.get(f"{self.api_base}/agents")
            if response.status_code == 401:
                self.results.add_pass("Missing authorization header properly rejected")
            else:
                self.results.add_fail(
                    "Authentication bypass",
                    f"Missing auth header should return 401, got {response.status_code}",
                    severity="critical"
                )
            
            # Test invalid authorization format
            invalid_auth_headers = [
                "Basic dGVzdDp0ZXN0",  # Basic auth instead of Bearer
                "Bearer",  # Missing token
                "Token abc123",  # Wrong scheme
                "Bearer " + "a" * 1000,  # Extremely long token
            ]
            
            for auth_header in invalid_auth_headers:
                headers = {"Authorization": auth_header}
                response = self.session.get(f"{self.api_base}/agents", headers=headers)
                
                if response.status_code == 401:
                    self.results.add_pass(f"Invalid auth format rejected: {auth_header[:20]}...")
                else:
                    self.results.add_fail(
                        "Authentication bypass",
                        f"Invalid auth format should return 401: {auth_header[:20]}...",
                        severity="high"
                    )
                    
        except Exception as e:
            self.results.add_fail("Authentication bypass test", f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run complete security validation suite."""
        print("🔒 STARTING COMPREHENSIVE SECURITY VALIDATION")
        print("="*80)
        
        test_methods = [
            self.test_health_endpoint_accessibility,
            self.test_jwt_authentication_flow,
            self.test_token_validation_security,
            self.test_scope_based_authorization,
            self.test_input_validation_and_sanitization,
            self.test_rate_limiting,
            self.test_security_headers,
            self.test_error_information_disclosure,
            self.test_audit_logging,
            self.test_authentication_bypass_attempts,
        ]
        
        for test_method in test_methods:
            try:
                print(f"\n🧪 Running {test_method.__name__.replace('test_', '').replace('_', ' ').title()}...")
                test_method()
            except Exception as e:
                self.results.add_fail(
                    test_method.__name__,
                    f"Test framework error: {str(e)}",
                    severity="critical"
                )
        
        self.results.print_summary()
        return self.results


def main():
    """Main security validation entry point."""
    print("🔍 Ordinaut Security Validation Suite")
    print("="*80)
    
    # Check if API is accessible
    try:
        response = requests.get(f"{TEST_API_BASE}/health", timeout=10)
        if response.status_code != 200:
            print(f"❌ API not accessible at {TEST_API_BASE}")
            print("   Please ensure the API is running with: docker-compose up -d")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {TEST_API_BASE}")
        print("   Please ensure the API is running with: docker-compose up -d")
        return False
    
    # Run security validation
    validator = SecurityValidator(TEST_API_BASE, TEST_DATABASE_URL)
    results = validator.run_all_tests()
    
    # Return success/failure based on results
    return results.failed == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)