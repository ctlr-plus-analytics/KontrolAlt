with open("tests/test_compute_velocity.py", "r", encoding="utf-8") as f:
    code = f.read()

target = """    def upsert(
        self, data: dict[str, object], on_conflict: str
    ) -> "_FakeQuery":
        self.upsert_data = data
        return self"""

replacement = """    def upsert(
        self, data: dict[str, object], on_conflict: str
    ) -> "_FakeQuery":
        self.upsert_data = data
        return self

    def update(self, data: dict[str, object]) -> "_FakeQuery":
        self.upsert_data = data
        return self"""

if target in code:
    code = code.replace(target, replacement)
    print("Patched test_compute_velocity.py (LF)")
elif target.replace("\n", "\r\n") in code:
    code = code.replace(target.replace("\n", "\r\n"), replacement.replace("\n", "\r\n"))
    print("Patched test_compute_velocity.py (CRLF)")

with open("tests/test_compute_velocity.py", "w", encoding="utf-8") as f:
    f.write(code)

# Patch test_run_daily_scrape.py
with open("tests/test_run_daily_scrape.py", "r", encoding="utf-8") as f:
    code2 = f.read()

target2 = """    signatures = [FakeSignature() for _ in range(9)]
    staged = _stage_scrape_signatures(signatures)"""

replacement2 = """    signatures = [FakeSignature() for _ in range(9)]
    staged = _stage_scrape_signatures([("dummy", sig) for sig in signatures])"""

if target2 in code2:
    code2 = code2.replace(target2, replacement2)
    print("Patched test_run_daily_scrape.py (LF)")
elif target2.replace("\n", "\r\n") in code2:
    code2 = code2.replace(target2.replace("\n", "\r\n"), replacement2.replace("\n", "\r\n"))
    print("Patched test_run_daily_scrape.py (CRLF)")
else:
    print("Target not found in test_run_daily_scrape.py")

with open("tests/test_run_daily_scrape.py", "w", encoding="utf-8") as f:
    f.write(code2)
