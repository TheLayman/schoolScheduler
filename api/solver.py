import json
from pulp import LpProblem, LpVariable, LpBinary, lpSum, LpStatus, value, PULP_CBC_CMD

# ----------------------------
# Load JSON configuration data
# ----------------------------
with open('schedule-config.json', 'r') as f:
    data = json.load(f)

num_classes = data['numClasses']
subject_teacher_mappings = data['subjectTeacherMappings']
subject_period_mappings = data['subjectPeriodMappings']
group_classes = data.get('groupClasses', [])

# Define days and periods
days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
num_periods_per_day = 7
num_periods_per_week = num_periods_per_day * len(days)

# ---------------------------------------------------------
# Build data structures for subjects per class and teachers
# ---------------------------------------------------------
# Map each class to its subjects and assigned teacher.
# subjects_per_class[class_id] is a dict { subject: teacher }
subjects_per_class = {i: {} for i in range(1, num_classes + 1)}
for mapping in subject_teacher_mappings:
    class_id = mapping['class']
    subject = mapping['subject']
    teacher = mapping['teacher']
    subjects_per_class[class_id][subject] = teacher

# For each class, record the required number of periods per subject.
subject_periods = {i: {} for i in range(1, num_classes + 1)}
for mapping in subject_period_mappings:
    class_id = mapping['class']
    subject = mapping['subject']
    periods = mapping['periodsPerWeek']
    subject_periods[class_id][subject] = periods

# ---------------------------------------------------------------
# Identify group subject assignments (subjects taught as a group)
# ---------------------------------------------------------------
# For each group session, mark (class, subject) as a group assignment.
group_assignments = set()
for group in group_classes:
    subject = group['subject']
    for class_id in group['classes']:
        group_assignments.add((class_id, subject))

# -------------------------------
# Create the MILP model using PuLP
# -------------------------------
# (We use a dummy objective since this is a feasibility problem.)
model = LpProblem("Scheduling", sense=1)  # sense=1 for minimization
model += 0, "DummyObjective"

# ----------------------------------------------------------------
# Create decision variables:
# schedule[(class, subject, period)] is a binary variable that is 1 if the subject is scheduled
# in that period for that class.
# ----------------------------------------------------------------
schedule = {}
for class_id in subjects_per_class:
    for subject in subjects_per_class[class_id]:
        for period in range(num_periods_per_week):
            var_name = f'class_{class_id}_{subject}_p{period}'
            schedule[(class_id, subject, period)] = LpVariable(var_name, cat=LpBinary)

# ------------------------------------------------------------
# Add subject period requirements for non-group subjects.
# ------------------------------------------------------------
for class_id in subjects_per_class:
    for subject in subjects_per_class[class_id]:
        if (class_id, subject) in group_assignments:
            continue  # Group sessions handled separately.
        periods_needed = subject_periods[class_id].get(subject, 0)
        model += (lpSum(schedule[(class_id, subject, p)] for p in range(num_periods_per_week))
                  == periods_needed), f"PeriodRequirement_class{class_id}_{subject}"

# -----------------------------------------------------------
# Prepare teacher assignments for individual and group subjects.
# -----------------------------------------------------------
teacher_individual = {}
for mapping in subject_teacher_mappings:
    class_id = mapping['class']
    subject = mapping['subject']
    teacher = mapping['teacher']
    if (class_id, subject) not in group_assignments:
        teacher_individual.setdefault(teacher, []).append((class_id, subject))

teacher_group = {}
# For group subjects, assign a unique index (g_idx) per group.
for g_idx, group in enumerate(group_classes):
    teacher = group['teacher']
    teacher_group.setdefault(teacher, set()).add(g_idx)

# -------------------------------------------------------------------------
# Process group classes:
# For each group session, create one binary variable per period.
# Tie each involved class's variable for that subject to the group variable.
# Enforce that the total sessions equal the group requirement.
# If "selectedSlots" is provided, only allow sessions in those periods.
# -------------------------------------------------------------------------
group_vars = {}          # (g_idx, period) -> binary variable for the group session.
group_period_vars = {}   # g_idx -> list of group variables (across periods).
for g_idx, group in enumerate(group_classes):
    subject = group['subject']
    classes = group['classes']
    periods_needed = group['periodsPerWeek']
    selectedSlots = group.get('selectedSlots')
    allowed = set(x - 1 for x in selectedSlots) if selectedSlots is not None else None
    group_period_vars[g_idx] = []
    for period in range(num_periods_per_week):
        var_name = f'group_{subject}_g{g_idx}_p{period}'
        group_var = LpVariable(var_name, cat=LpBinary)
        if allowed is not None and period not in allowed:
            model += group_var == 0, f"GroupSlotNotAllowed_g{g_idx}_p{period}"
        # Tie each involved class's schedule variable for the subject to group_var.
        for class_id in classes:
            model += (schedule[(class_id, subject, period)] == group_var), f"GroupTie_class{class_id}_{subject}_g{g_idx}_p{period}"
        group_vars[(g_idx, period)] = group_var
        group_period_vars[g_idx].append(group_var)
    model += (lpSum(group_period_vars[g_idx]) == periods_needed), f"GroupPeriodRequirement_g{g_idx}"

# ------------------------------------------------------------------------------
# Enforce that each class has at most one subject scheduled per period.
# ------------------------------------------------------------------------------
for class_id in subjects_per_class:
    for period in range(num_periods_per_week):
        model += (lpSum(schedule[(class_id, subject, period)]
                        for subject in subjects_per_class[class_id]) <= 1), f"OneSubjectPerPeriod_class{class_id}_p{period}"

# ------------------------------------------------------------
# Teacher availability constraints:
# A teacher cannot be scheduled in more than one place in the same period.
# ------------------------------------------------------------------------------
all_teachers = set(list(teacher_individual.keys()) + list(teacher_group.keys()))
for teacher in all_teachers:
    for period in range(num_periods_per_week):
        vars_list = []
        if teacher in teacher_individual:
            vars_list += [schedule[(class_id, subject, period)]
                          for (class_id, subject) in teacher_individual[teacher]]
        if teacher in teacher_group:
            for g_idx in teacher_group[teacher]:
                vars_list.append(group_vars[(g_idx, period)])
        model += (lpSum(vars_list) <= 1), f"TeacherAvailability_{teacher}_p{period}"

# -------------------------
# Solve the scheduling model
# -------------------------
solver = PULP_CBC_CMD(msg=0)
model.solve(solver)

if LpStatus[model.status] not in ['Optimal', 'Feasible']:
    print("No solution found!")
    exit(1)

# -----------------------------------------------------
# Generate the class schedule in a nested dictionary format.
# schedule_table[day][period] is a dict mapping "Class X" -> "Subject (Teacher)"
# -----------------------------------------------------
schedule_table = {day: {f'Period {p+1}': {} for p in range(num_periods_per_day)} for day in days}
for class_id in subjects_per_class:
    for subject in subjects_per_class[class_id]:
        teacher = subjects_per_class[class_id][subject]
        for period in range(num_periods_per_week):
            if value(schedule[(class_id, subject, period)]) == 1:
                day = days[period // num_periods_per_day]
                slot = f'Period {period % num_periods_per_day + 1}'
                schedule_table[day][slot][f'Class {class_id}'] = f"{subject} ({teacher})"

# -----------------------------------------------------------------------------------
# Print the class timetables in a simple tabular text format.
# -----------------------------------------------------------------------------------
print("Class Timetables:")
for class_id in range(1, num_classes + 1):
    print(f"\nClass {class_id} Timetable:")
    # Print header row
    header = "Period".ljust(10) + "".join(day.ljust(20) for day in days)
    print(header)
    for period in range(1, num_periods_per_day + 1):
        row = f"Period {period}".ljust(10)
        for day in days:
            cell_text = schedule_table[day][f'Period {period}'].get(f'Class {class_id}', '')
            row += cell_text.ljust(20)
        print(row)

# -----------------------------------------------------------------------------------
# Generate and print teacher timetables.
# For each teacher, print a table with:
#   - Rows: Days of the week
#   - Columns: Periods (Period 1 ... Period 7)
# Each cell shows "Class X: Subject" (or a combined list for group sessions)
# -----------------------------------------------------------------------------------
print("\nTeacher Timetables:")
all_teachers_set = set(mapping['teacher'] for mapping in subject_teacher_mappings)
for teacher in sorted(all_teachers_set):
    print(f"\nTeacher: {teacher}")
    header = "Day".ljust(12) + "".join(f"P{p+1}".ljust(20) for p in range(num_periods_per_day))
    print(header)
    for day_index, day in enumerate(days):
        row = day.ljust(12)
        for p in range(num_periods_per_day):
            period_index = day_index * num_periods_per_day + p
            assignments = []
            for class_id in range(1, num_classes + 1):
                for subject in subjects_per_class[class_id]:
                    if subjects_per_class[class_id][subject] == teacher:
                        if value(schedule[(class_id, subject, period_index)]) == 1:
                            assignments.append((class_id, subject))
            if assignments:
                subjects_in_cell = {sub for (_, sub) in assignments}
                if len(subjects_in_cell) == 1:
                    subject_name = subjects_in_cell.pop()
                    classes_in_cell = sorted({cls for (cls, _) in assignments})
                    cell_text = f"Class {','.join(map(str, classes_in_cell))}: {subject_name}"
                else:
                    cell_text = "; ".join(f"Class {cls}: {sub}" for (cls, sub) in assignments)
            else:
                cell_text = ""
            row += cell_text.ljust(20)
        print(row)
