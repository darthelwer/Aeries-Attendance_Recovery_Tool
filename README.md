# Attendance Recovery Tool for Aeries

GitHub: https://github.com/darthelwer/Attendance-Recovery-In-Aeries

Created by Adam Elwer: https://github.com/darthelwer



- ***For the love of all things holy, please read this document before using the software.*** 
- It contains important setup information and assumptions used by the application.       -



## SUPPORT FUTURE MAINTENANCE AND DEVELOPMENT!

This started as me trying to find a solution to a problem in our district, and it blossomed into this project using my nights and weekends.

If this tool saved your district hours of manual work and you'd like to support future development, or just support my Dr Pepper Zero habit:

Venmo: `@darthelwer`

---

## DISCLAIMER

This tool is not affiliated with or endorsed by Aeries Software.

This tool updates attendance records in Aeries. Always review the generated CSV and test in a non-production environment before updating production data.

Your LEA is responsible for ensuring compliance with California Education Code and any local attendance policies.

---

## WELCOME

If you used my original steps and tool, and you've been waiting for improvements, thanks for hanging in there.

This application automates the Attendance Recovery workflow while still allowing you to review every change before anything is written back to Aeries.

This app:

* Loads supplemental and daily attendance.
* Reads Supplemental Attendance Sessions from Aeries.
* Limits sessions to whole-hour increments as required by California Education Code.
* Combines multiple shorter sessions to reach required minutes for Attendance Recovery under Education Code by grade.
* Matches Attendance Recovery days to absences.
* Checks for previously applied Attendance Recovery days and when they were used.
* Limits the total number of Attendance Recovery days to 10 per student.
* Allows you to choose which Supplemental Attendance Sessions to include by school.
* Allows you to choose which absence codes qualify for Attendance Recovery.

  * This assumes your district is pushing attendance codes from school `0` to all other schools.
  * If that is not the case, please reach out for help.
* Allows you to configure the ADA Make Up Code written to `ATT.ADA`.

  * The Aeries default is usually `M`, but some districts may use something else.
* Creates CSV output for internal auditing before making changes to student records.
* Creates CSV output that can also be provided to auditors.
* Can generate either:

  * **NEW Records Only** — records not already applied to Aeries.
  * **ALL Matching Records** — all calculated matches for audit/review.
* Adds the actual attendance date next to the Aeries attendance day using the `DAY` table.
* Creates automatic log files for troubleshooting and audit review.
* Optionally uploads reviewed NEW records directly to the `ATT` table in Aeries.
* Uses a SQL transaction during upload.
* Rolls back the upload if an error occurs.

---

## THIS IS A PYTHON FILE

Sorry, I ran into some issues creating this as an EXE. Some districts that I tested this with, including my own, have a lot of restrictions against running EXE files made by PyInstaller.

I'm working on sorting this out, but I know we have deadlines fast approaching.

You will need:

* The latest version of Python.
* One Python library:

  * `pyodbc` — used for talking to SQL Server.
* Microsoft ODBC Driver 18 for SQL Server.

  * This can be downloaded directly from Microsoft and will be checked for on startup.
* The app also uses a JSON config file to store information between uses, such as:

  * Server name
  * Database name
  * Username
  * School year
  * Attendance Recovery settings

The config file does **not** store your SQL password.

I have removed the *sample.json* file as the program will now create one on start up.
I have a few other tools in the works and will point to this same config file for those 
programs as well. I do not curently have plans to create the ability to access multiple 
database configurations. If thats something you need put in a feature request through the 
app or on the github page.

---

## CONFIGURATION

The app includes a **Config** menu where you can review and update connection settings.

The connection configuration includes:

* Database Display Name
* School Year
* Server Name
* Database Name
* Username
* ODBC Driver

The server, database, and username fields should come from Aeries or whoever manages your Aeries SQL access.

The app also includes a database preview so you can confirm which database name will be used for the selected school year.

Example:

```text
DST25000FallbrookUnionESD
```

The application can also check whether Microsoft ODBC Driver 18 for SQL Server appears to be installed.

---

## SUPPLEMENTAL ATTENDANCE SESSIONS

In Aeries, these are called **Supplemental Attendance Sessions**.

The tool reads these from the `ATS` table.

When generating records, you choose which schools and Supplemental Attendance Sessions to include.

The tool does **not** remember these selections on purpose.

Supplemental Attendance Sessions can change from year to year, and users should think about what they are including each time they run the tool.

---

## ATTENDANCE CODES

The tool reads district-level attendance codes from:

```sql
ABS
WHERE SC = 0
  AND DEL = 0
```

Most districts push district attendance codes from school `0` to all schools.

If your district configures attendance codes separately by school, this version may not handle your setup correctly. Please review carefully before use.

The tool stores your selected qualifying absence codes in the JSON config file.

---

## AERIES UPLOAD RESULTS

Successful Attendance Recovery days appear in Aeries as:

* Green attendance indicators
* Green attendance boxes
* ADA Make-up Notes

The attendance comment includes:

* ADA Make Up Code
* Supplemental Attendance Session name
* Date or dates used to recover the absence

Examples:

```text
Super Summer Camp: 07/24/2025

T1 ASES ELOP: 09/03/25 09/04/25 09/05/25 09/08/25
```

The ADA Make Up Code is configurable. The default is usually:

```text
M
```

---

## IMPORTANT NOTE ON SUPPLEMENTAL ATTENDANCE SESSION NAMES!

The `ATT.ACO` field in Aeries is limited to 50 characters.

Our auditors wanted both the Supplemental Attendance Session name and all dates used for the Attendance Recovery.

Example:

We had to shorten:

```text
Trimester 1 ASES ELOP After School Genius Hour
```

to:

```text
T1 ASES ELOP
```

I did **NOT** name that, by the way.

If a Supplemental Attendance Session name combined with multiple recovery dates exceeds this limit, the application will stop and display an error noting the following:

* School
* Session `SE`
* Supplemental Attendance Session name
* Maximum allowable session name length

  * This is 50 minus the characters needed for the dates and formatting.

The message will tell you to shorten the Supplemental Attendance Session name in Aeries before continuing.

It will **not** let you proceed until the issue is resolved.

---

## LOG FILES

The tool creates log files so districts have a better record of what happened during a run.

Logs may include:

* Tool version
* Database display name
* Database name
* School year
* SQL user
* Selected schools
* Selected Supplemental Attendance Sessions
* Selected attendance codes
* ADA Make Up Code
* CSV file path
* Number of records generated
* Number of records uploaded
* Records already correct
* Errors or warnings
* Rollback details if an upload fails

There is also a **Save Log** option so you can save a copy somewhere else, such as an audit folder or shared drive.

This is especially helpful when troubleshooting. Instead of trying to recreate everything from memory, you can send or review the log file.

---

## UPLOAD SAFETY

The application intentionally pauses before updating Aeries so you can review the generated CSV.

Please verify:

* Student ID list
* Absence dates
* Attendance Recovery dates
* Attendance comments
* Supplemental Attendance Sessions selected
* Attendance codes selected

Only continue with the SQL upload once you are satisfied the CSV is correct.

Uploads are done inside a SQL transaction.

If an upload error occurs, the application will roll back the entire upload and report the record that caused the issue when possible.

That means the tool is designed to avoid partially updating Aeries if something goes wrong.

---

## WHAT THIS PROGRAM DOES NOT DO

This application does not:

* Import your Supplemental Attendance into Aeries if it is stored in spreadsheets.

  * Sorry.
* Verify Supplemental Attendance class size or student/teacher ratios.

  * Currently 10:1 for TK/K and 20:1 for all others.
  * They **will** be looking at this.
* Validate compliance with California Education Code beyond the attendance matching logic implemented in this application.
* Divide Attendance Recovery into reporting periods such as P1, P2, and EOY.

If you need the data sorted by P1, P2, or EOY, you can sort the generated CSV by `ATT.DY` or `ATT.DY(DT)`.

You will need to know which Aeries attendance day corresponds to each instructional day in your own district calendar.

This was a level of complexity I was not ready to add because the relationship between Aeries day, instructional days, and dates is not consistent from district to district.

For example, in my district, the P2 date of March 20 is instructional day 132 but Aeries attendance day 160.

---

## BEFORE UPLOADING

The application intentionally pauses before updating Aeries so you can review the generated CSV.

Please verify:

* Student ID list
* Absence dates
* Attendance Recovery dates
* Attendance comments
* Supplemental Attendance Sessions selected
* Attendance codes selected
* ADA Make Up Code

Only continue with the SQL upload once you are satisfied the CSV is correct.

---

## ISSUES, IDEAS, CONTRIBUTIONS, AND COLLABORATION

If you find a bug, have an idea for a new feature, or your district has a unique Attendance Recovery workflow, please open an Issue on GitHub.

If your district, county, or Aeries would like to collaborate on this or other features, please reach out to me at:

```text
adamelwer [AT] gmail [DOT] com
```

Feedback from other districts helps improve the application for everyone.

Thank you for reading this to the end! I hope this saves you time, energy, and stress.

May the force be with you, always!

---

# Version History

## 1.0.2

Public GitHub release replacing the original 1.0.0 workflow.

1.0.1 was used for internal testing with schools and was not published to GitHub.

Added:

* Config menu updates.
* Cleaner connection configuration.
* Database Display Name.
* Live database name preview.
* Microsoft ODBC Driver 18 detection.
* Driver status display.
* Supplemental Attendance Session terminology.
* Ability to load Supplemental Attendance Sessions from `ATS`.
* School/session selection interface.
* District attendance code loading from `ABS`.
* Attendance code selection.
* Configurable ADA Make Up Code for `ATT.ADA`.
* NEW Records Only CSV mode.
* ALL Matching Records CSV mode.
* Upload limited to reviewed NEW records.
* `ATT.DY(DT)` column using the `DAY` table.
* `ATT.ACO` length validation.
* Automatic run log files.
* Save Log option.
* Collapsible log panel.
* Improved upload summary.
* SQL transaction rollback on upload errors.
* Offending record details when upload fails, when available.
* Version/status display improvements.
* Reload Supplemental Attendance Sessions moved under the Connection menu.
* Improved school/session scrolling and visual separation in the main window.

Changed:

* Renamed user-facing “program” language to **Supplemental Attendance Sessions** where appropriate.
* Simplified the Connection menu.
* Renamed Configuration menu to **Config**.
* Improved review-before-upload workflow.
* Improved CSV output for audit use.
* Improved handling of transfer students by using attendance record school/student number data where needed.

No packaging changes were included in this release.

## 1.0.1

Internal testing build only.

This version was tested with schools but was not published to GitHub.

## 1.0.0

Initial public GUI release.

Added:

* Direct SQL upload.
* Attendance code configuration.
* Automatic audit CSV generation.
* Duplicate detection and prevention.
* Basic GUI workflow.
* School/program selection.
* CSV review before upload.
