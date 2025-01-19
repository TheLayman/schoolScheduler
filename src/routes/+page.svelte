``<script lang="ts">
  import { onMount } from 'svelte';
  import LoadingOverlay from '$lib/components/LoadingOverlay.svelte';
  import ErrorPopup from '$lib/components/ErrorPopup.svelte';
  import html2canvas from 'html2canvas';
  
  // Define interfaces for our data structures
  interface Subject {
    subject: string;
    periodsPerWeek: number;
  }

  interface ClassSubject {
    class: number;
    subjects: Subject[];
  }

  interface TeacherAssignment {
    teacher: string;
    classes: number[];
    subject: string;
  }

  interface ScheduleSlot {
    teacher: string;
    subject: string;
  }

  // Type for the schedule array
  type ScheduleGrid = Array<Array<Array<ScheduleSlot | null>>>;

  let isLoading = false;
  let numClasses = 5;
  let isGenerating = false;
  let errorMessage = '';
  let teachers: string[] = [];
  let newTeacher = '';
  let schedule: ScheduleGrid = [];
  let teacherAssignments: TeacherAssignment[] = [];
  let classSubjects: ClassSubject[] = [];

  const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const PERIODS_PER_DAY = 7;

  let generationStartTime: number = 0;
  let elapsedTime: string = '0:00';
  let generationStatus: string = '';

  let showErrorPopup = false;
  let popupMessage = '';

  // Lazy load the worker
  let worker: Worker;
  onMount(() => {
    if (!worker) {
      worker = new Worker(new URL('$lib/scheduleWorker.ts', import.meta.url), { type: 'module' });
    }
    
    return () => {
      if (worker) {
        worker.terminate();
      }
    };
  });

  function addTeacher() {
    if (newTeacher.trim()) {
      teachers = [...teachers, newTeacher.trim()];
      newTeacher = '';
    }
  }

  function removeTeacher(index: number) {
    teachers = teachers.filter((_, i) => i !== index);
  }

  function addAssignment() {
    teacherAssignments = [...teacherAssignments, {
      teacher: '',
      classes: [],
      subject: ''
    }];
  }

  function removeAssignment(index: number) {
    teacherAssignments = teacherAssignments.filter((_, i) => i !== index);
  }

  function addClassSubject() {
    classSubjects = [...classSubjects, {
      class: 1,
      subjects: []
    }];
  }

  function removeClassSubject(index: number) {
    classSubjects = classSubjects.filter((_, i) => i !== index);
  }

  function addSubjectToClass(classSubject: ClassSubject) {
    classSubject.subjects = [...classSubject.subjects, {
      subject: '',
      periodsPerWeek: 0
    }];
    classSubjects = [...classSubjects];
  }

  function removeSubjectFromClass(classSubject: ClassSubject, subjectIndex: number) {
    classSubject.subjects = classSubject.subjects.filter((_, i) => i !== subjectIndex);
    classSubjects = classSubjects;
  }

  function toggleClass(assignment: TeacherAssignment, classNum: number) {
    if (assignment.classes.includes(classNum)) {
      assignment.classes = assignment.classes.filter(c => c !== classNum);
    } else {
      assignment.classes = [...assignment.classes, classNum];
    }
    teacherAssignments = teacherAssignments;
  }

  function countSubjectPeriods(
    schedule: ScheduleGrid,
    classNum: number,
    subject: string
  ): number {
    let count = 0;
    for (let day = 0; day < DAYS.length; day++) {
      for (let period = 0; period < PERIODS_PER_DAY; period++) {
        if (schedule[day][period][classNum]?.subject === subject) {
          count++;
        }
      }
    }
    return count;
  }

  function findTeacherForSubject(subject: string, classNum: number): string | null {
    const assignment = teacherAssignments.find(a => 
      a.subject === subject && 
      a.classes.includes(classNum + 1)
    );
    return assignment?.teacher || null;
  }

  function updateTimer() {
    const elapsed = Math.floor((Date.now() - generationStartTime) / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    elapsedTime = `${minutes}:${seconds.toString().padStart(2, '0')}`;
  }

  function solveSchedule(
    schedule: ScheduleGrid,
    day: number = 0,
    period: number = 0,
    classNum: number = 0
  ): boolean {
    generationStatus = `Trying: Class ${classNum + 1}, Day ${DAYS[day] || ''}, Period ${period + 1}`;
    
    if (day >= DAYS.length) {
      for (const classSubject of classSubjects) {
        for (const subject of classSubject.subjects) {
          const actualPeriods = countSubjectPeriods(schedule, classSubject.class - 1, subject.subject);
          if (actualPeriods !== subject.periodsPerWeek) {
            return false;
          }
        }
      }
      return true;
    }

    let nextClass = (classNum + 1) % numClasses;
    let nextPeriod = nextClass === 0 ? period + 1 : period;
    let nextDay = nextPeriod >= PERIODS_PER_DAY ? day + 1 : day;
    nextPeriod = nextPeriod % PERIODS_PER_DAY;

    const classConfig = classSubjects.find(cs => cs.class === classNum + 1);
    if (!classConfig) {
      return solveSchedule(schedule, nextDay, nextPeriod, nextClass);
    }

    for (const subject of classConfig.subjects) {
      const currentCount = countSubjectPeriods(schedule, classNum, subject.subject);
      if (currentCount >= subject.periodsPerWeek) {
        continue;
      }

      const remainingSlots = (DAYS.length * PERIODS_PER_DAY) - 
        (day * PERIODS_PER_DAY + period + 1);
      const remainingRequired = subject.periodsPerWeek - currentCount;
      
      if (remainingRequired > remainingSlots) {
        continue;
      }

      const teacher = findTeacherForSubject(subject.subject, classNum);
      if (!teacher) {
        continue;
      }

      if (isValidAssignment(schedule, day, period, classNum, teacher, subject.subject)) {
        schedule[day][period][classNum] = { teacher, subject: subject.subject };
        
        if (solveSchedule(schedule, nextDay, nextPeriod, nextClass)) {
          return true;
        }
        
        schedule[day][period][classNum] = null;
      }
    }

    let canLeaveEmpty = true;
    for (const subject of classConfig.subjects) {
      const currentCount = countSubjectPeriods(schedule, classNum, subject.subject);
      const remainingSlots = (DAYS.length * PERIODS_PER_DAY) - 
        (day * PERIODS_PER_DAY + period + 1);
      const remainingRequired = subject.periodsPerWeek - currentCount;
      
      if (remainingRequired > remainingSlots) {
        canLeaveEmpty = false;
        break;
      }
    }

    if (canLeaveEmpty) {
      schedule[day][period][classNum] = null;
      if (solveSchedule(schedule, nextDay, nextPeriod, nextClass)) {
        return true;
      }
    }

    return false;
  }

  function closePopup() {
    showErrorPopup = false;
    popupMessage = '';
  }

  // Add type definitions for worker messages
  interface WorkerMessage {
    type: 'success' | 'error' | 'status' | 'log';
    data: any;
  }

  // Update handleWorkerMessage
  function handleWorkerMessage(event: MessageEvent<WorkerMessage>) {
    const { type, data } = event.data;
    
    switch (type) {
      case 'success':
        schedule = data.map((day: any[]) =>
          day.map((period: any[]) =>
            period.map((slot: any) => {
              if (!slot) return null;
              return {
                teacher: slot.teacher,
                subject: slot.subject
              };
            })
          )
        );
        isGenerating = false;
        break;
      case 'error':
        console.error('Schedule Generation Error:', data);
        errorMessage = data;
        isGenerating = false;
        break;
      case 'status':
        generationStatus = data;
        break;
      case 'log':
        console.log(data); // Print to browser console
        break;
    }
  }

  // New interfaces
  interface SubjectTeacherMapping {
    class: number;
    subject: string;
    teacher: string;
  }

  interface SubjectPeriodMapping {
    class: number;
    subject: string;
    periodsPerWeek: number;
  }

  interface ScheduleConfig {
    numClasses: number;
    subjectTeacherMappings: SubjectTeacherMapping[];
    subjectPeriodMappings: SubjectPeriodMapping[];
  }

  function prepareScheduleConfig(): ScheduleConfig {
    const subjectTeacherMappings: SubjectTeacherMapping[] = [];
    const subjectPeriodMappings: SubjectPeriodMapping[] = [];

    (teacherAssignments || []).forEach(assignment => {
      if (assignment.teacher && assignment.subject) {
        assignment.classes.forEach(classNum => {
          subjectTeacherMappings.push({
            class: classNum,
            subject: assignment.subject,
            teacher: assignment.teacher
          });
        });
      }
    });

    (classSubjects || []).forEach(cs => {
      if (cs.subjects) {
        cs.subjects.forEach(subject => {
          if (subject.subject) {
            subjectPeriodMappings.push({
              class: cs.class,
              subject: subject.subject,
              periodsPerWeek: subject.periodsPerWeek || 1
            });
          }
        });
      }
    });

    return {
      numClasses,
      subjectTeacherMappings,
      subjectPeriodMappings
    };
  }

  function loadScheduleConfig(config: ScheduleConfig) {
    numClasses = config.numClasses || 1;
    teacherAssignments = [];
    classSubjects = [];

    const uniqueTeachers = new Set(config.subjectTeacherMappings.map(m => m.teacher));
    teachers = Array.from(uniqueTeachers);

    const teacherMap = new Map<string, TeacherAssignment>();
    config.subjectTeacherMappings.forEach(mapping => {
      const key = `${mapping.teacher}-${mapping.subject}`;
      if (!teacherMap.has(key)) {
        teacherMap.set(key, {
          teacher: mapping.teacher,
          subject: mapping.subject,
          classes: [mapping.class]
        });
      } else {
        teacherMap.get(key)!.classes.push(mapping.class);
      }
    });
    teacherAssignments = Array.from(teacherMap.values());

    const classMap = new Map<number, ClassSubject>();
    config.subjectPeriodMappings.forEach(mapping => {
      if (!classMap.has(mapping.class)) {
        classMap.set(mapping.class, {
          class: mapping.class,
          subjects: []
        });
      }
      classMap.get(mapping.class)!.subjects.push({
        subject: mapping.subject,
        periodsPerWeek: mapping.periodsPerWeek
      });
    });
    classSubjects = Array.from(classMap.values());
  }

  function saveConfiguration() {
    const config = prepareScheduleConfig();
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'schedule-config.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function handleConfigUpload(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input?.files?.[0];
    
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const config = JSON.parse((e.target?.result as string) || '{}') as ScheduleConfig;
          loadScheduleConfig(config);
        } catch (error) {
          errorMessage = 'Error loading configuration: Invalid file format';
        }
      };
      reader.readAsText(file);
    }
  }

  async function generateSchedule() {
    try {
      isGenerating = true;
      errorMessage = '';
      showErrorPopup = false;

      const config = prepareScheduleConfig();
      
      if (!worker) {
        worker = new Worker(new URL('$lib/scheduleWorker.ts', import.meta.url), { type: 'module' });
      }

      worker.onmessage = handleWorkerMessage;
      worker.onerror = (error) => {
        console.error('Worker Error:', error);
        errorMessage = error.message;
        isGenerating = false;
      };

      worker.postMessage({
        ...config,
        DAYS,
        PERIODS_PER_DAY
      });

    } catch (error) {
      console.error('Error:', error);
      errorMessage = error instanceof Error ? error.message : 'An unexpected error occurred';
      isGenerating = false;
    }
  }

  async function downloadScheduleImage(classIndex: number) {
    const tableElement = document.getElementById(`schedule-table-${classIndex}`);
    if (!tableElement) return;

    try {
      const canvas = await html2canvas(tableElement, {
        backgroundColor: '#ffffff',
        scale: 2, // Higher quality
      });

      const link = document.createElement('a');
      link.download = `Class-${classIndex + 1}-Schedule.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (error) {
      console.error('Error generating image:', error);
    }
  }

  function isValidAssignment(
    schedule: ScheduleGrid,
    day: number,
    period: number,
    classNum: number,
    teacher: string,
    subject: string
  ): boolean {
    for (let c = 0; c < numClasses; c++) {
      if (c !== classNum && schedule[day][period][c]?.teacher === teacher) {
        return false;
      }
    }

    let teacherPeriodsInDay = 0;
    for (let p = 0; p < PERIODS_PER_DAY; p++) {
      for (let c = 0; c < numClasses; c++) {
        if (schedule[day][p][c]?.teacher === teacher) {
          teacherPeriodsInDay++;
        }
      }
    }
    if (teacherPeriodsInDay >= PERIODS_PER_DAY - 1) {
      return false;
    }

    return true;
  }
</script>

{#if isLoading}
  <div class="flex items-center justify-center min-h-screen">
    <div class="text-xl">Loading...</div>
  </div>
{:else}
  <main class="container mx-auto p-4">
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-2xl font-bold">School Schedule Generator</h1>
      <label class="bg-purple-500 text-white px-4 py-2 rounded cursor-pointer">
        Load Config
        <input
          type="file"
          accept=".json"
          on:change={handleConfigUpload}
          class="hidden"
        />
      </label>
    </div>

    <!-- Number of Classes Input -->
    <section class="mb-8">
      <h2 class="text-xl font-semibold mb-4">Configuration</h2>
      <div class="flex gap-2 items-center">
        <label for="numClasses" class="font-medium">Number of Classes:</label>
        <input
          id="numClasses"
          type="number"
          bind:value={numClasses}
          min="1"
          max="10"
          class="border p-2 rounded w-24"
        />
      </div>
    </section>

    <!-- Teacher Input Section -->
    <section class="mb-8">
      <h2 class="text-xl font-semibold mb-4">Teachers</h2>
      <div class="flex gap-2 mb-4">
        <input
          type="text"
          bind:value={newTeacher}
          placeholder="Enter teacher name"
          class="border p-2 rounded"
        />
        <button
          on:click={addTeacher}
          class="bg-blue-500 text-white px-4 py-2 rounded"
        >
          Add Teacher
        </button>
      </div>
      <ul class="space-y-2">
        {#each teachers as teacher, i}
          <li class="flex items-center gap-2">
            <span>{teacher}</span>
            <button
              on:click={() => removeTeacher(i)}
              class="text-red-500"
            >
              Remove
            </button>
          </li>
        {/each}
      </ul>
    </section>

    <!-- Teacher-Subject-Class Assignment Section -->
    <section class="mb-8">
      <h2 class="text-xl font-semibold mb-4">Teacher Assignments</h2>
      <button
        on:click={addAssignment}
        class="bg-green-500 text-white px-4 py-2 rounded mb-4"
      >
        Add Assignment
      </button>
      <div class="space-y-4">
        {#each teacherAssignments as assignment, i}
          <div class="flex flex-col gap-4">
            <div class="flex gap-4 items-center">
              <select
                bind:value={assignment.teacher}
                class="border p-2 rounded"
              >
                <option value="">Select Teacher</option>
                {#each teachers as teacher}
                  <option value={teacher}>{teacher}</option>
                {/each}
              </select>
              <input
                type="text"
                bind:value={assignment.subject}
                placeholder="Subject"
                class="border p-2 rounded"
              />
              <button
                on:click={() => removeAssignment(i)}
                class="text-red-500"
              >
                Remove
              </button>
            </div>
            <div class="flex gap-2 flex-wrap pl-4">
              {#each Array(numClasses) as _, i}
                <label class="flex items-center gap-2 border rounded p-2 cursor-pointer hover:bg-gray-50">
                  <input
                    type="checkbox"
                    checked={assignment.classes.includes(i + 1)}
                    on:change={() => toggleClass(assignment, i + 1)}
                  />
                  Class {i + 1}
                </label>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </section>

    <!-- Class-Subject-Periods Section -->
    <section class="mb-8">
      <h2 class="text-xl font-semibold mb-4">Class Subjects and Periods</h2>
      <button
        on:click={addClassSubject}
        class="bg-green-500 text-white px-4 py-2 rounded mb-4"
      >
        Add Class
      </button>
      <div class="space-y-6">
        {#each classSubjects as classSubject, i}
          <div class="border rounded-lg p-4">
            <div class="flex gap-4 items-center mb-4">
              <select
                bind:value={classSubject.class}
                class="border p-2 rounded"
              >
                {#each Array(numClasses) as _, i}
                  <option value={i + 1}>Class {i + 1}</option>
                {/each}
              </select>
              <button
                on:click={() => removeClassSubject(i)}
                class="text-red-500"
              >
                Remove Class
              </button>
            </div>
            
            <div class="pl-4 space-y-4">
              <button
                on:click={() => addSubjectToClass(classSubject)}
                class="bg-blue-500 text-white px-3 py-1 rounded text-sm"
              >
                Add Subject
              </button>
              
              {#each classSubject.subjects as subjectData, subjectIndex}
                <div class="flex gap-4 items-center">
                  <input
                    type="text"
                    bind:value={subjectData.subject}
                    placeholder="Subject Name"
                    class="border p-2 rounded"
                  />
                  <input
                    type="number"
                    bind:value={subjectData.periodsPerWeek}
                    min="1"
                    max="42"
                    class="border p-2 rounded w-24"
                  />
                  <button
                    on:click={() => removeSubjectFromClass(classSubject, subjectIndex)}
                    class="text-red-500"
                  >
                    Remove
                  </button>
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </section>

    <div class="flex gap-4">
      <button
        on:click={saveConfiguration}
        class="bg-purple-500 text-white px-4 py-2 rounded"
      >
        Save Config
      </button>
      <button
        on:click={generateSchedule}
        class="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold"
        disabled={isGenerating}
      >
        {isGenerating ? 'Generating...' : 'Generate Schedule'}
      </button>
    </div>

    {#if errorMessage}
      <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-8">
        {errorMessage}
      </div>
    {/if}

    {#if schedule.length > 0}
      <section class="mb-8">
        <h2 class="text-xl font-semibold mb-4">Generated Schedule</h2>
        
        <!-- Create a table for each class -->
        {#each Array(numClasses) as _, classIndex}
          <div class="mb-8">
            <div class="flex justify-between items-center mb-2">
              <h3 class="text-lg font-semibold">Class {classIndex + 1}</h3>
              <button
                on:click={() => downloadScheduleImage(classIndex)}
                class="text-gray-600 hover:text-gray-800 p-2 rounded-lg transition-colors border border-gray-300 hover:border-gray-400 bg-white shadow-sm"
                aria-label="Download schedule for Class {classIndex + 1}"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd" />
                </svg>
              </button>
            </div>
            <div class="overflow-x-auto" id="schedule-table-{classIndex}">
              <table class="min-w-full border-collapse border border-gray-300 bg-white">
                <thead>
                  <tr>
                    <th class="border border-gray-300 p-2 bg-gray-100">Period/Day</th>
                    {#each DAYS as day}
                      <th class="border border-gray-300 p-2 bg-gray-100">{day}</th>
                    {/each}
                  </tr>
                </thead>
                <tbody>
                  {#each Array(PERIODS_PER_DAY) as _, periodIndex}
                    <tr>
                      <td class="border border-gray-300 p-2 font-medium bg-gray-50">
                        Period {periodIndex + 1}
                      </td>
                      {#each DAYS as _, dayIndex}
                        <td class="border border-gray-300 p-2 text-center">
                          {#if schedule[dayIndex][periodIndex][classIndex]}
                            {schedule[dayIndex][periodIndex][classIndex].subject}
                            <br>
                            <span class="text-sm text-gray-600">({schedule[dayIndex][periodIndex][classIndex].teacher})</span>
                          {:else}
                            -
                          {/if}
                        </td>
                      {/each}
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        {/each}
      </section>
    {/if}

    {#if isGenerating}
      <LoadingOverlay message={generationStatus} />
    {/if}

    {#if showErrorPopup}
      <ErrorPopup 
        message={popupMessage} 
        onClose={closePopup} 
      />
    {/if}
  </main>
{/if}

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
  }
</style>
