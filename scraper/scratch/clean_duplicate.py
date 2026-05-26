# Clean duplicate method in test_compute_velocity.py
with open("tests/test_compute_velocity.py", "r", encoding="utf-8") as f:
    code = f.read()

double_method = """    def update(self, data: dict[str, object]) -> "_FakeQuery":
        self.upsert_data = data
        return self

    def update(self, data: dict[str, object]) -> "_FakeQuery":
        self.upsert_data = data
        return self"""

single_method = """    def update(self, data: dict[str, object]) -> "_FakeQuery":
        self.upsert_data = data
        return self"""

if double_method in code:
    code = code.replace(double_method, single_method)
    print("Cleaned double method (LF)")
elif double_method.replace("\n", "\r\n") in code:
    code = code.replace(double_method.replace("\n", "\r\n"), single_method.replace("\n", "\r\n"))
    print("Cleaned double method (CRLF)")
else:
    print("Double method not found")

with open("tests/test_compute_velocity.py", "w", encoding="utf-8") as f:
    f.write(code)
