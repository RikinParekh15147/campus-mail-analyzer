const { test, expect, _electron } = require("@playwright/test");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
test("desktop provides a real isolated Python workflow", async () => {
  test.setTimeout(120000);
  const data = await fs.mkdtemp(path.join(os.tmpdir(), "campus-desktop-"));
  const root = path.resolve(__dirname, "../..");
  const executablePath = process.env.CAMPUS_PACKAGED_EXECUTABLE;
  const desktop = await _electron.launch({
    ...(executablePath ? { executablePath } : {}),
    args: executablePath ? [] : [path.join(root, "desktop")],
    env: {
      ...process.env,
      CAMPUS_DATA_DIR: data,
      CAMPUS_PYTHON: path.join(root, ".venv/bin/python"),
    },
  });
  try {
    const page = await desktop.firstWindow();
    await page.waitForLoadState();
    await page
      .getByPlaceholder("What should we call you?")
      .fill("Demo Student");
    await page.getByRole("button", { name: /Create my workspace/ }).click();
    await expect(
      page.getByRole("heading", { name: "A little clarity, Demo." }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Analyze a notice" }).click();
    await page
      .getByPlaceholder("Course / notice subject")
      .fill("NLP201 Assignment 2");
    await page
      .getByPlaceholder("Paste the original text here…")
      .fill(
        "NLP201 Assignment 2 must submit by 25 October 2026. Instructions: https://example.edu/task.pdf",
      );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Analyze notice" })
      .click();
    await page.locator(".nav-item").filter({ hasText: "Assignments" }).click();
    await expect(
      page.getByRole("heading", { name: "NLP201 Assignment 2", exact: true }),
    ).toBeVisible();
    await page.locator(".nav-item").filter({ hasText: "Profile" }).click();
    await page.getByRole("button", { name: "Add a confirmed detail" }).click();
    await page.getByRole("dialog").locator("input").nth(0).fill("roll_number");
    await page.getByRole("dialog").locator("input").nth(1).fill("23BIT044");
    await page.getByRole("button", { name: "Confirm detail" }).click();
    await expect(page.getByText("23BIT044", { exact: true })).toBeVisible();
    await page.locator(".nav-item").filter({ hasText: "Marks" }).click();
    await page.getByRole("button", { name: "Extract results" }).click();
    await page.getByPlaceholder("NLP201", { exact: true }).fill("NLP201");
    await page.getByPlaceholder("Midsem / Quiz 1").fill("Quiz 1");
    await page.getByRole("dialog").locator("textarea").fill("23BIT044 8/10");
    await page.getByRole("button", { name: "Find my result" }).click();
    await expect(page.getByText("8 / 10", { exact: true })).toBeVisible();
    await page.locator(".nav-item").filter({ hasText: "Calendar" }).click();
    const localToday = (
      await page.evaluate(() => window.campus.request("/summary"))
    ).date;
    const shifted = (n) => {
      const d = new Date(localToday + "T12:00:00Z");
      d.setUTCDate(d.getUTCDate() + n);
      return d.toISOString().slice(0, 10);
    };
    const classDay = shifted(2);
    const weekday = (new Date(classDay + "T12:00:00Z").getUTCDay() + 6) % 7;
    await page.getByRole("button", { name: "Import timetable" }).click();
    const schedule = {
      schema_version: "1.0",
      timezone: "Asia/Kolkata",
      student_context: { batch: "B" },
      term_start: localToday,
      term_end: shifted(90),
      sessions: [
        { course: "NLP201", weekday, start: "09:00", end: "10:00", batch: "B" },
      ],
    };
    await page
      .getByPlaceholder("Paste schema-valid JSON…")
      .fill(JSON.stringify(schedule));
    await page.getByRole("button", { name: "Validate & preview" }).click();
    await expect(page.locator(".import-preview")).toContainText("NLP201");
    await page.getByRole("button", { name: "Confirm and activate" }).click();
    await page.getByRole("button", { name: "Plan a block" }).click();
    await page.getByLabel("What are you planning?").fill("Study NLP201");
    await page.getByLabel("Start", { exact: true }).fill(classDay + "T09:00");
    await page.getByLabel("End", { exact: true }).fill(classDay + "T10:00");
    await page.getByRole("button", { name: "Add personal block" }).click();
    await expect(page.locator(".conflict-card")).toContainText("Study NLP201");
    await page.getByRole("button", { name: "Suggest another slot" }).click();
    await expect(page.getByRole("dialog")).toContainText(
      "Nothing has moved yet",
    );
    await page.getByRole("button", { name: "Approve this change" }).click();
    await expect(page.locator(".quiet-state")).toContainText(
      "No known conflicts",
    );
    for (const screen of [
      "Calendar",
      "Events",
      "Resources",
      "Replies",
      "Review",
      "Models",
      "Settings",
      "Today",
    ]) {
      await page
        .locator(".nav-item")
        .filter({ hasText: new RegExp("^" + screen) })
        .click();
      await expect(page.locator(".page-heading h1")).toBeVisible();
    }
    await fs.mkdir(path.join(root, "artifacts/screenshots"), {
      recursive: true,
    });
    await page.screenshot({
      path: path.join(root, "artifacts/screenshots/dashboard.png"),
      fullPage: true,
    });
  } finally {
    await desktop.close();
    await fs.rm(data, { recursive: true, force: true });
  }
});
