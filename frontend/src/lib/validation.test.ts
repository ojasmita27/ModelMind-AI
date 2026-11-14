import { describe, expect, it } from "vitest";
import { validateDescription, validateEmail, validateNewPassword, validateProjectName } from "./validation";

describe("validation mirrors backend rules", () => {
  it("email", () => {
    expect(validateEmail("")).toMatch(/Enter your email/);
    expect(validateEmail("nope")).toMatch(/valid email/);
    expect(validateEmail("a@b.co")).toBeNull();
  });
  it("password length 8..128", () => {
    expect(validateNewPassword("1234567")).toMatch(/at least 8/);
    expect(validateNewPassword("12345678")).toBeNull();
    expect(validateNewPassword("x".repeat(128))).toBeNull();
    expect(validateNewPassword("x".repeat(129))).toMatch(/at most 128/);
  });
  it("project name 1..120 after trimming, description <= 2000", () => {
    expect(validateProjectName("   ")).toMatch(/name/);
    expect(validateProjectName("x".repeat(121))).toMatch(/120/);
    expect(validateProjectName(" ok ")).toBeNull();
    expect(validateDescription("d".repeat(2001))).toMatch(/2000/);
    expect(validateDescription("")).toBeNull();
  });
});
