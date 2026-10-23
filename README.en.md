# HaoJob

[简体中文](README.md) · **English**

HaoJob lets **Codex** or **Claude Code** help with your job search: finding jobs, editing your resume, applying, tracking results, and preparing for interviews. It works only from your own materials, cites a source for every statement it writes, and keeps anything you haven't done out of your resume.

![Demo: Claude Code writes a resume bullet from fictional notes, lists the claims it deliberately left out, and cites a source for each statement](docs/assets/demo.gif)

> Alpha: nobody outside the project has tried it yet, so start with the fictional examples in this repository.

Chinese is the primary documentation language. The prompts below are in English, but most linked guides are in Chinese; you can ask the agent to explain them.

## What it is

HaoJob is not an app you install. It is a job-search playbook written for the AI (called a *Skill*), plus blank templates and a few small tools. You tell Codex or Claude Code what you want in plain words, and the agent follows the playbook. It comes from the workflow the maintainer used throughout their own job search.

Your resume, project notes, and application records stay in a `private/` folder on your computer, which is never committed to Git.

The workflow has four steps, and you can use any of them on its own:

```text
① Set up your materials → ② Find jobs that match your profile → ③ Apply once authorized → ④ Track, follow up, prepare for interviews
```

## Try it in 5 minutes

Start with the fictional materials in this repository. You don't need a real resume or a recruiting-site account.

You need: [Claude Code](https://code.claude.com/docs/en/setup) (runs in a terminal) or the Codex desktop app, plus Git and Python 3.10 or later. It has been tried on macOS and Linux, not yet on Windows.

1. Get the repository from a terminal:

   ```sh
   git clone https://github.com/HaoPan036/hao-job.git
   cd hao-job
   ```

2. Open the folder with your agent:
   - **Claude Code**: run `claude` in the same terminal.
   - **Codex**: sign in following the [official setup guide](https://learn.chatgpt.com/docs/quickstart), then open this folder.

3. Send it this request:

   ```text
   Use the hao-job Skill.
   The project notes are in examples/walkthrough/source.md.
   The job description is in examples/walkthrough/target-role.md.
   Based on those materials, write one resume bullet in Chinese and English.
   Then help me explain this project in an interview, in English.
   Separately show which source supports each important statement
   and what still needs confirmation.
   Reply in this conversation; do not modify any files.
   ```

You'll get a resume bullet in both languages, an interview explanation, the source behind each statement, and the claims it deliberately left out. To keep practicing, try the [full fictional exercise](examples/walkthrough/README.md).

If the agent says it can't find the Skill, ask it to read `.agents/skills/hao-job/SKILL.md` first. To use it from folders outside this repository, see the [install notes](tools/skill-install/README.md) (in Chinese).

## The full workflow

### ① Set up your materials

**What you do:** in Claude Code, type `/setup`; in Codex, say "set up my job-search materials". It first creates `private/` and confirms it stays out of Git, then asks you to paste your resume or **copy** your resume and project notes into `private/inbox/`. Add real materials only after that check passes.

**What the agent does:**

1. Creates a blank workspace in `private/` and confirms the folder stays out of Git.
2. Reads your materials and splits each experience into "fact cards", one claim per card, each naming the file it came from.
3. Asks a few groups of questions: target roles, regions, work authorization in each region, graduation and start dates, and which parts of each project you did yourself. You can skip any of them.
4. Writes your job-search preferences to `private/job-search/profile.json`. Step ② searches with these.
5. Ends with a list of things for you to confirm.

**Where it gets stuck:**

- **PDF and Word resumes may not be readable.** Markdown and plain text work best for now; if reading fails, save your resume as plain text and try again.
- **Everything read from a resume starts as unverified.** Only claims you confirm one by one go into real resumes. Results with numbers stay unverified until you can say how they were measured.
- **It won't guess your work authorization or graduation date.** Anything you don't state stays blank, and in step ② jobs that depend on it go to you for a decision.
- If the check finds `private/` isn't ignored by Git, it stops and uses only fictional materials until that's fixed.

To do it step by step yourself, see the [setup guide](tools/workspace/README.md) (in Chinese).

### ② Find jobs that match your profile

**What you do:** say "Find a few jobs that match my preferences. Check the official listings and tell me which are worth applying to. Don't save anything or apply yet."

**What the agent does:**

1. Reads the roles, regions, and conditions in `profile.json` and uses its own web search to find candidates.
2. Checks each job on the company's career site or official applicant system: is it still open, what does it require, do your work authorization and dates fit.
3. Compares against jobs you've applied to or already queued, and drops duplicates.
4. Gives each job a recommendation (apply now, apply in a batch, needs your call, watch, or skip) with reasons and which resume to use.
5. Only shows you the results by default. When you say "save", it adds the worthwhile ones to your queue in `private/recruiting/queue.md`.

**Optional: automatic collection.** To keep watching specific companies, list their career pages, RSS feeds, Greenhouse, Lever and similar addresses in `private/job-search/sources.json`, then use the [job radar](tools/job-radar/README.md) to collect candidates for the agent to check one by one. It never queues or applies on its own.

**Where it gets stuck:**

- **An empty `profile.json` gives it nothing to search for.** Do step ① first, or just tell the agent your roles and regions.
- **The agent needs web search.** Whether it can search, and how well, depends on your Codex or Claude Code account and settings.
- **Aggregators, social posts, and old screenshots are only leads.** It has to open the official job page before recommending an application.
- **Jobs with unclear conditions aren't let through automatically.** For example, if a posting doesn't mention visa sponsorship and you haven't stated your work authorization, it marks the job for your decision.
- **The automatic sources list starts empty**, and you fill in the addresses. It can't handle pages that need a login or load content in the browser, and compatibility with real sites hasn't been checked site by site. Scheduled runs and change monitoring are experimental and have only been simulated on macOS; see the [background service notes](docs/experimental/background-service.md) (in Chinese).

### ③ Apply once authorized

**What you do:** first run the [local mock application](examples/application/README.md): following its steps, you start a fake recruiting site on your computer and the agent fills, checks, and submits a fictional application. Nothing goes to a real site. This step needs an agent that can control a browser. For a real application, name the exact job:

```text
I authorize you to apply to this specific job: [official link and job ID].
Use the materials I confirmed in private/ and this resume: [file path].
After filling it in, have an independent agent check the actual page,
submit once if it passes, then update my records.
Stop if I need to register, sign in, or answer something you're unsure of.
Do not apply to any other job.
```

If you only want the form filled, say "fill it in but don't submit".

**What the agent does:**

1. Checks whether you've applied to this job before.
2. Opens the page, fills in the form, and uploads the resume you named.
3. Hands it to a second agent, which checks the actual page: every field, each declaration ticked, and the uploaded files, against your authorization and materials.
4. If the check passes, that agent clicks submit once and confirms the site shows success. It doesn't ask "are you sure?" again.

**Where it gets stuck:**

- **Registration, sign-in, and captchas** are yours to do. It stops on that page and tells you.
- **Required questions your materials don't answer** (expected salary, a specific declaration) make it stop and ask you rather than make something up.
- **The agent needs to control a browser.** So far this has only worked end to end with Codex and local Chrome on the mock site. Browser use in Claude Code and real recruiting sites haven't been validated and may get stuck on a given site.
- **If no second agent is available**, it keeps the filled draft and doesn't submit after checking its own work.
- **If the page hangs after submit and success is unclear**, it doesn't click again or count it as a success; it asks you to check on the site first.
- Some sites send your data as you fill in or upload, not only when you submit.

Full steps are in the [application guide](docs/applications.md) (in Chinese).

### ④ Track, follow up, prepare for interviews

**What the agent does:**

- After a confirmed submission, updates your application history and queue, counts applications, and saves the exact resume you submitted.
- When you get an assessment, interview invitation, rejection, or offer, paste it in and it updates your records and next steps. It doesn't read your email or reply for you.
- Before an interview, say "find the resume I used for this job and prepare my project explanation from it", and it retrieves the original, not a later edit.
- Prepares project explanations, likely follow-up questions, technical topics, and one-question-at-a-time mock interviews.

**Where it gets stuck:**

- Application counts are grouped by region, and the template's Singapore / Canada are only examples. Tell the agent your regions during `/setup` and it updates `private/recruiting/config.json`; until then, applications in other regions aren't counted and the audit reports a problem.
- If the counts report problems, fix those first or the numbers may be incomplete. See the [sync tool](tools/recruiting-sync/README.md) (in Chinese).

Blank templates for resumes, cover letters, interview prep and review are in [templates](templates/); the [interview example](examples/walkthrough/interview-cycle.md) shows how they fit together.

## How it guards against overstatement

A [fictional example](examples/timeout/source.md):

> Notes: I wrote the retry and stop rules; after the program timed out, it tried once more, timed out again, and stopped.
>
> What an AI tends to write: Solved a performance problem.
>
> Revised against the notes: Added retry and stop rules so the program stops after two timed-out attempts.

The agent can still make mistakes, so read the output before you use it.

## Privacy

Don't commit real materials to a public repository or issue. Files stored locally aren't necessarily processed only locally once the agent reads them, and filling a web form can send content to the recruiting site before you submit. See the [data notes](docs/privacy-and-data-flow.md) (in Chinese).

## Feedback and license

After trying it, please report back with the [tryout template](docs/tryout.md) in [Issues](https://github.com/HaoPan036/hao-job/issues/new), without attaching a real resume. What has and hasn't been tested is in the [environment notes](docs/supported-environments.md) and [validation plan](docs/validation-plan.md); a comparison with similar projects is in the [sources notes](docs/sources.md) (all in Chinese).

Licensed under [MIT](LICENSE).
