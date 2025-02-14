import json
import matplotlib.pyplot as plt
from ortools.sat.python import cp_model
import os

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
num_periods_per_week = num_periods_per_day * len(days)  # e.g., 40 periods

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
# Create the CP-SAT model object
# -------------------------------
model = cp_model.CpModel()

# ----------------------------------------------------------------
# Create decision variables:
# schedule[(class, subject, period)] is a binary variable that is 1 if the subject is scheduled
# in that period for that class.
# ----------------------------------------------------------------
schedule = {}
for class_id in subjects_per_class:
    for subject in subjects_per_class[class_id]:
        for period in range(num_periods_per_week):
            schedule[(class_id, subject, period)] = model.NewBoolVar(
                f'class_{class_id}_{subject}_p{period}'
            )

# ------------------------------------------------------------
# Add subject period requirements for non-group subjects.
# ------------------------------------------------------------
for class_id in subjects_per_class:
    for subject in subjects_per_class[class_id]:
        if (class_id, subject) in group_assignments:
            continue  # Group sessions handled separately.
        periods_needed = subject_periods[class_id].get(subject, 0)
        model.Add(sum(schedule[(class_id, subject, p)] for p in range(num_periods_per_week))
                  == periods_needed)

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
    selectedSlots = [x-1 for x in group.get('selectedSlots', None)]  # Allowed period indices, if provided.
    group_period_vars[g_idx] = []
    for period in range(num_periods_per_week):
        group_var = model.NewBoolVar(f'group_{subject}_g{g_idx}_p{period}')
        if selectedSlots is not None and period not in selectedSlots:
            model.Add(group_var == 0)
        # For each involved class, tie its scheduling variable to the group variable.
        for class_id in classes:
            model.Add(schedule[(class_id, subject, period)] == group_var)
        group_vars[(g_idx, period)] = group_var
        group_period_vars[g_idx].append(group_var)
    model.Add(sum(group_period_vars[g_idx]) == periods_needed)

# ------------------------------------------------------------------------------
# Enforce that each class has at most one subject scheduled per period.
# ------------------------------------------------------------------------------
for class_id in subjects_per_class:
    for period in range(num_periods_per_week):
        model.Add(sum(schedule[(class_id, subject, period)]
                      for subject in subjects_per_class[class_id]) <= 1)

# ------------------------------------------------------------
# Teacher availability constraints:
# A teacher cannot be scheduled in more than one place in the same period.
# For each period, sum the individual schedule variables and the group variables.
# ------------------------------------------------------------------------------
all_teachers = set(list(teacher_individual.keys()) + list(teacher_group.keys()))
for teacher in all_teachers:
    for period in range(num_periods_per_week):
        vars_list = []
        if teacher in teacher_individual:
            vars_list += [schedule[(class_id, subject, period)]
                          for (class_id, subject) in teacher_individual[teacher]]
        if teacher in teacher_group:
            vars_list += [group_vars[(g_idx, period)] for g_idx in teacher_group[teacher]]
        model.Add(sum(vars_list) <= 1)

# -------------------------
# Solve the scheduling model
# -------------------------
solver = cp_model.CpSolver()
status = solver.Solve(model)
if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
    print("No solution found!")
    exit(1)

# -----------------------------------------------------
# Generate the class schedule in a nested dictionary format.
# schedule_table[day][period] is a dict mapping "Class X" -> "Subject (Teacher)"
# -----------------------------------------------------
def generate_class_schedule():
    schedule_table = {day: {f'Period {p+1}': {} for p in range(num_periods_per_day)} for day in days}
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            teacher = subjects_per_class[class_id][subject]
            for period in range(num_periods_per_week):
                if solver.Value(schedule[(class_id, subject, period)]) == 1:
                    day = days[period // num_periods_per_day]
                    slot = f'Period {period % num_periods_per_day + 1}'
                    schedule_table[day][slot][f'Class {class_id}'] = f"{subject} ({teacher})"
    return schedule_table

class_schedule = generate_class_schedule()

# -----------------------------------------------------------------------------------
# Generate and save one JPEG per class.
# The table has:
#   - Rows: Periods (Period 1 ... Period 8)
#   - Columns: Days (Monday ... Friday)
# Each cell shows "Subject (Teacher)"
# -----------------------------------------------------------------------------------
for class_id in range(1, num_classes + 1):
    # Build a table: rows (periods), columns (days)
    table_data = []
    for period in range(1, num_periods_per_day + 1):
        row = []
        for day in days:
            cell_text = class_schedule[day][f'Period {period}'].get(f'Class {class_id}', '')
            row.append(cell_text)
        table_data.append(row)
    # Create the table using matplotlib.
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis('tight')
    ax.axis('off')
    column_labels = days
    row_labels = [f'Period {i}' for i in range(1, num_periods_per_day + 1)]
    table = ax.table(cellText=table_data,
                     colLabels=column_labels,
                     rowLabels=row_labels,
                     cellLoc='center',
                     loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    fig.tight_layout()
    results_dir = 'Schedules'
    if not os.path.isdir(results_dir):
        os.makedirs(results_dir)
    filename = os.path.join(results_dir, f'class_{class_id}_schedule.png')
    plt.savefig(filename)
    plt.close(fig)
    print(f"Class {class_id} schedule saved as {filename}")

# -----------------------------------------------------------------------------------
# Generate teacher timetables.
# For each teacher, create a table with:
#   - Rows: Days of the week
#   - Columns: Periods (Period 1 ... Period 8)
# Each cell shows "Class X: Subject" (or for group sessions, a combined list if multiple classes)
# -----------------------------------------------------------------------------------
# Get the set of all teachers from the subject mappings.
all_teachers_set = set(mapping['teacher'] for mapping in subject_teacher_mappings)

for teacher in all_teachers_set:
    # Build a 2D list: rows=days, columns=periods.
    teacher_table = []
    for day_index, day in enumerate(days):
        row = []
        for p in range(num_periods_per_day):
            period_index = day_index * num_periods_per_day + p
            assignments = []
            # Look through every class and subject taught by this teacher.
            for class_id in range(1, num_classes + 1):
                for subject in subjects_per_class[class_id]:
                    if subjects_per_class[class_id][subject] == teacher:
                        if solver.Value(schedule[(class_id, subject, period_index)]) == 1:
                            assignments.append((class_id, subject))
            # Combine assignments if more than one (e.g. group session across classes).
            if assignments:
                # If all assignments have the same subject, combine class numbers.
                subjects_in_cell = {sub for (_, sub) in assignments}
                if len(subjects_in_cell) == 1:
                    subject_name = subjects_in_cell.pop()
                    classes_in_cell = sorted({cls for (cls, _) in assignments})
                    cell_text = f"Class {','.join(map(str, classes_in_cell))}: {subject_name}"
                else:
                    # If, unexpectedly, multiple different subjects appear, list them separately.
                    cell_text = "\n".join(f"Class {cls}: {sub}" for (cls, sub) in assignments)
            else:
                cell_text = ""
            row.append(cell_text)
        teacher_table.append(row)
    
    # Create a matplotlib table with:
    #   - Row labels: Days
    #   - Column labels: Period 1, Period 2, ..., Period 8
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis('tight')
    ax.axis('off')
    column_labels = [f'Period {i}' for i in range(1, num_periods_per_day + 1)]
    row_labels = days
    table = ax.table(cellText=teacher_table,
                     colLabels=column_labels,
                     rowLabels=row_labels,
                     cellLoc='center',
                     loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    fig.tight_layout()
    # Replace spaces in teacher name for the filename.
    safe_teacher = teacher.replace(" ", "_")
    results_dir = 'Schedules'
    if not os.path.isdir(results_dir):
        os.makedirs(results_dir)
    filename = os.path.join(results_dir, f'teacher_{safe_teacher}_timetable.png')
    plt.savefig(filename)
    plt.close(fig)
    print(f"Teacher {teacher} timetable saved as {filename}")
