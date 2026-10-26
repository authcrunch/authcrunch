#!/usr/bin/env python3
"""Real browser interactions; no mocked authentication or injected login state."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from e2e_login import SCENARIOS, now, redact, write_json

ACCESS_COOKIE = "AUTHP_ACCESS_TOKEN"
PROTECTED = '[data-testid="protected-content"]'
USERNAME = 'input[name="username"]'
PASSWORD = 'input[name="secret"]'


class Journey:
    def __init__(self, browser, output, origin, profile, password):
        self.browser, self.root, self.origin = browser, output, origin
        self.profile, self.password = profile, password
        self.output = output / profile
        self.output.mkdir()
        self.records = [{"id": name, "status": "not-run", "steps": [], "checks": []} for name in SCENARIOS]
        self.context, self.page, self.case = None, None, None
        self.token = None
        self.save()

    def save(self):
        write_json(self.output / "results.json", self.records)

    def check(self, condition, description, observed=None):
        self.case["checks"].append({"description": description, "passed": bool(condition), "observed": observed})
        self.save()
        if not condition:
            raise AssertionError(description + (f"; observed: {observed}" if observed is not None else ""))

    def capture(self, label):
        number = len(self.case["steps"])
        prefix = f"{self.case['id']}/{number:02d}"
        png = self.output / (prefix + ".png")
        png.parent.mkdir(exist_ok=True)
        self.page.screenshot(path=str(png), full_page=True, animations="disabled", timeout=8000)
        # Save inert markup for diagnosis, with hidden credentials removed.
        markup = self.page.evaluate("""() => {
            const clone = document.documentElement.cloneNode(true);
            clone.querySelectorAll('input').forEach(n => n.removeAttribute('value'));
            return clone.outerHTML;
        }""")
        source = self.output / (prefix + ".html.txt")
        source.write_text(redact(markup, [self.password]))
        return {"label": label, "at": now(), "url": self.page.url,
                "screenshot": str(png.relative_to(self.root)), "source": str(source.relative_to(self.root))}

    @contextmanager
    def step(self, label):
        step = {"label": label, "status": "running", "at": now()}
        self.case["steps"].append(step)
        self.save()
        started = time.monotonic()
        try:
            yield
            step.update(self.capture(label), status="passed")
        except Exception as error:
            step.update(status="failed", error=str(error))
            try:
                step.update(self.capture(label))
            except Exception as capture_error:
                step["capture_error"] = str(capture_error)
            raise
        finally:
            step["duration_ms"] = round((time.monotonic() - started) * 1000)
            self.save()

    def denied(self):
        expect(self.page.locator(USERNAME)).to_be_visible()
        expect(self.page.locator(PROTECTED)).to_have_count(0)
        self.check(urlsplit(self.page.url).path == "/auth/login", "Protected resource redirects to the login form", self.page.url)

    def submit(self):
        # A browser click submits the actual form and waits for real navigation.
        with self.page.expect_navigation(wait_until="load") as navigation:
            self.page.locator('button[type="submit"]').click()
        return navigation.value

    def username(self):
        with self.step("Enter the username"):
            self.page.locator(USERNAME).fill("jsmith")
            self.check(self.page.locator(USERNAME).input_value() == "jsmith", "Username is entered in the real login form")
        with self.step("Continue to the password challenge"):
            response = self.submit()
            self.check(response is not None and response.status == 200, "Username submission returns the password challenge")
            expect(self.page.locator(PASSWORD)).to_be_visible()
            self.check(self.page.locator(PASSWORD).get_attribute("type") == "password", "Password field masks typed characters")

    def cookies(self):
        return self.context.cookies(self.origin)

    def invalid_password(self):
        with self.step("Open the login page in a fresh browser context"):
            self.page.goto(self.origin + "/auth/login")
            self.denied()
        self.username()
        with self.step("Submit an incorrect password"):
            self.page.locator(PASSWORD).fill("Deliberately-wrong-password!42")
            response = self.submit()
            self.check(response is not None and response.status == 401, "Incorrect password receives HTTP 401",
                       response.status if response else None)
            expect(self.page.locator("body")).to_contain_text(re.compile("authentication failed", re.I))
            self.check(not any(c["name"] == ACCESS_COOKIE for c in self.cookies()), "Rejected login issues no access cookie")
        with self.step("Confirm rejected credentials cannot open the application"):
            self.page.goto(self.origin + "/protected")
            self.denied()

    def login_session_logout(self):
        with self.step("An anonymous visitor is redirected to sign in"):
            self.page.goto(self.origin + "/protected")
            self.denied()
        self.username()
        with self.step("Enter the password"):
            self.page.locator(PASSWORD).fill(self.password)
            self.check(bool(self.page.locator(PASSWORD).input_value()), "Password is entered into the browser form")
        with self.step("Submit credentials and return to the protected application"):
            self.submit()
            expect(self.page).to_have_url(self.origin + "/protected")
            expect(self.page.locator(PROTECTED)).to_be_visible()
            access = next((c for c in self.cookies() if c["name"] == ACCESS_COOKIE), None)
            self.check(access is not None, "Successful login issues an access cookie")
            self.check(access["secure"], "Access cookie is Secure")
            self.check(access["httpOnly"], "Access cookie is HttpOnly")
            self.check(access["sameSite"] in ("Lax", "Strict"), "Access cookie has a SameSite policy", access["sameSite"])
            self.token = access["value"]
            self.case["cookies"] = [{k: v for k, v in c.items() if k != "value"} for c in self.cookies()]
        with self.step("Inspect the identity served by AuthCrunch"):
            self.page.goto(self.origin + "/auth/whoami")
            identity = json.loads(self.page.locator("pre code").inner_text())
            self.check(identity.get("authenticated") is True, "Server confirms an authenticated identity")
            self.check(identity.get("sub") == "jsmith", "Authenticated subject matches the submitted username", identity.get("sub"))
            # The local identity provider renders its name claim as Last, First.
            self.check(identity.get("name") == "Smith, John", "Authenticated name identifies John Smith", identity.get("name"))
            self.check("authp/user" in identity.get("roles", []), "Authenticated identity has the required role", identity.get("roles"))
            write_json(self.output / "identity.json", identity)
        with self.step("Reload the application without entering credentials again"):
            self.page.goto(self.origin + "/protected")
            response = self.page.reload()
            self.check(response.status == 200, "Authenticated reload returns HTTP 200", response.status)
            expect(self.page.locator(PROTECTED)).to_be_visible()
        with self.step("Open the application in a second tab"):
            other = self.context.new_page()
            other.goto(self.origin + "/protected")
            expect(other.locator(PROTECTED)).to_be_visible()
            self.check(True, "A second tab uses the existing browser session")
            self.page = other
        with self.step("Open the authenticated portal"):
            self.page.get_by_role("link", name="Open portal", exact=True).click()
            expect(self.page.locator('a[href="/auth/logout"]')).to_be_visible()
        with self.step("Sign out through the portal link"):
            self.page.locator('a[href="/auth/logout"]').click()
            expect(self.page.locator(USERNAME)).to_be_visible()
            self.check(not any(c["name"] == ACCESS_COOKIE for c in self.cookies()), "Logout removes the browser access cookie")
        with self.step("The application requires login after sign-out"):
            self.page.goto(self.origin + "/protected")
            self.denied()
        clean = self.browser.new_context(ignore_https_errors=True)
        previous_page = self.page
        try:
            with self.step("A new browser context also requires login"):
                fresh = clean.new_page()
                self.page = fresh
                fresh.goto(self.origin + "/protected")
                expect(fresh.locator(USERNAME)).to_be_visible()
                expect(fresh.locator(PROTECTED)).to_have_count(0)
                self.check(True, "A fresh browser has no authenticated session")
        finally:
            self.page = previous_page
            clean.close()

    def tampered_cookie(self):
        self.check(self.token is not None, "A real issued cookie is available for the signature rejection check")
        header, payload, signature = self.token.split(".")
        # Change a significant signature character; trailing base64 padding bits
        # can decode identically and would not be a meaningful negative control.
        signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        self.context.add_cookies([{"name": ACCESS_COOKIE, "value": f"{header}.{payload}.{signature}",
                                   "url": self.origin, "secure": True, "httpOnly": True, "sameSite": "Lax"}])
        with self.step("Reject a session cookie with a modified signature"):
            self.page.goto(self.origin + "/protected")
            self.denied()

    def run_case(self, identifier):
        self.case = next(c for c in self.records if c["id"] == identifier)
        self.case.update(status="running", started_at=now())
        directory = self.output / identifier
        directory.mkdir(exist_ok=True)
        events, page_errors, bad_responses, blocked, network_errors = [], [], [], [], []
        self.case["events"] = str((directory / "network.json").relative_to(self.root))
        self.save()
        started = time.monotonic()
        try:
            viewport = {"width": 1440, "height": 1000} if self.profile == "desktop" else {"width": 390, "height": 844}
            self.context = self.browser.new_context(viewport=viewport, device_scale_factor=1,
                is_mobile=self.profile == "mobile", has_touch=self.profile == "mobile",
                ignore_https_errors=True, locale="en-US", color_scheme="light", reduced_motion="reduce")
            self.context.set_default_timeout(10000)
            self.context.set_default_navigation_timeout(15000)
            self.context.tracing.start(screenshots=True, snapshots=True, sources=False)

            def event(kind, **fields):
                events.append(dict(at=now(), kind=kind, **fields))
                write_json(directory / "network.json", events)

            def route(request_route):
                url = request_route.request.url
                if url.startswith(self.origin + "/"):
                    request_route.continue_()
                else:
                    blocked.append(url)
                    request_route.abort()

            def response_received(response):
                event("response", url=response.url, status=response.status, method=response.request.method,
                      resource=response.request.resource_type)
                if response.status >= 500 or (response.status >= 400 and response.request.resource_type in ("stylesheet", "script", "font", "image")):
                    bad_responses.append(f"{response.status} {response.url}")

            def attach(page):
                page.on("console", lambda message: event("console", level=message.type, text=message.text))
                page.on("pageerror", lambda error: page_errors.append(str(error)))

            def request_failed(request):
                event("request-failed", url=request.url, error=request.failure)
                # Navigation may legitimately cancel an outstanding login probe.
                if request.failure != "net::ERR_ABORTED":
                    network_errors.append(f"{request.failure}: {request.url}")

            self.context.route("**/*", route)
            self.context.on("page", attach)
            self.context.on("request", lambda request: event("request", url=request.url, method=request.method,
                                                             resource=request.resource_type))
            self.context.on("response", response_received)
            self.context.on("requestfailed", request_failed)
            self.page = self.context.new_page()
            getattr(self, identifier.replace("-", "_"))()
            self.check(not page_errors, "No uncaught browser JavaScript errors", page_errors)
            self.check(not bad_responses, "No server errors or missing browser assets", bad_responses)
            self.check(not network_errors, "No unexpected browser network failures", network_errors)
            self.check(not blocked, "All browser traffic stays on the isolated instance", blocked)
            self.case["status"] = "passed"
        except Exception as error:
            self.case.update(status="failed", error=redact(str(error), [self.password]))
            (directory / "error.txt").write_text(redact(traceback.format_exc(), [self.password]))
        finally:
            self.case.update(duration_ms=round((time.monotonic() - started) * 1000), finished_at=now(),
                             page_errors=page_errors, bad_responses=bad_responses, blocked_requests=blocked,
                             network_errors=network_errors)
            if self.context:
                try:
                    trace = directory / "trace.zip"
                    self.context.tracing.stop(path=str(trace))
                    self.case["trace"] = str(trace.relative_to(self.root))
                    self.context.close()
                except Exception as error:
                    self.case.update(status="failed", cleanup_error=str(error))
                self.context = None
            self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--profile", required=True, choices=("desktop", "mobile"))
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            journey = Journey(browser, args.output, args.origin, args.profile, os.environ["E2E_LOGIN_PASSWORD"])
            write_json(journey.output / "browser.json", {"engine": "chromium", "version": browser.version,
                                                        "profile": args.profile})
            for identifier in SCENARIOS:
                journey.run_case(identifier)
            return 0 if all(c["status"] == "passed" for c in journey.records) else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
