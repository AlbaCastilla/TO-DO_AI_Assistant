
#to save tasks locally in a json file
import json
from pathlib import Path

import ollama
import streamlit as st

# Configuration
MODEL = "qwen2.5:3b"
TASKS_FILE = Path(__file__).with_name("tasks.json")

st.title("To-Do AI Assistant")
st.caption("Add[task] priority[High/Medium/Low] due[date] | Delete[task number/name] | Complete[task number/name] | List[all/pending/completed tasks]")

#load tasks from the json file
def load_tasks():
    if TASKS_FILE.exists():
        with open(TASKS_FILE, "r", encoding="utf-8") as file:
            tasks = json.load(file)

        # Add default values to older tasks if they don't have the fields
        for task in tasks:
            task.setdefault("priority", "Medium")
            task.setdefault("due_date", "tomorrow")
            task.setdefault("completed", False)

        return tasks

    return []

#save tasks to json file
def save_tasks(tasks):
    TASKS_FILE.write_text(
        json.dumps(tasks, indent=2),
        encoding="utf-8"
    )

#add new task to rhe list
def add_task(title, priority="Medium", due_date="Not specified"):
    tasks = load_tasks()

    tasks.append({
        "title": title,
        "priority": priority.capitalize(),
        "due_date": due_date,
        "done": False
    })

    save_tasks(tasks)
    return f"Added task: {title}"



#list tasks with optional dropdown filter
def list_tasks(status="all"):
    tasks = load_tasks()
    #load all tasks unless the user choses pending or completed tasks 
    if status == "pending":
        tasks = [task for task in tasks if not task["done"]]
    elif status == "completed":
        tasks = [task for task in tasks if task["done"]]

    if not tasks:
        return "No tasks found."

    result = []

    for i, task in enumerate(tasks, start=1):
        state = "Completed" if task["done"] else "Pending"

        result.append(
            f"{i}. {task['title']} | "
            f"Priority: {task['priority']} | "
            f"Due: {task['due_date']} | "
            f"Status: {state}"
        )

    return "\n".join(result)

#complete a task by its number
def complete_task(task_number):
    tasks = load_tasks()
    index = task_number - 1

    if index < 0 or index >= len(tasks):
        return "Task number does not exist."

    tasks[index]["done"] = True
    save_tasks(tasks)

    return f"Completed task: {tasks[index]['title']}"

#delete a task by its number
def delete_task(task_number):
    tasks = load_tasks()
    index = task_number - 1

    if index < 0 or index >= len(tasks):
        return "Task number does not exist."

    deleted = tasks.pop(index)
    save_tasks(tasks)

    return f"Deleted task: {deleted['title']}"



#list of tools available to the AI agent, with their descriptions and parameters
tools = [
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a new task with an optional priority and due date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["High", "Medium", "Low"]
                    },
                    "due_date": {"type": "string"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Show tasks. Filter by all, pending or completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "pending", "completed"]
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as completed using its number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_number": {"type": "integer"}
                },
                "required": ["task_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Delete a task using its number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_number": {"type": "integer"}
                },
                "required": ["task_number"]
            }
        }
    }
]


# Connect tool names to Py funnctions
available_functions = {
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "delete_task": delete_task
}



#AI agent loop that processes user requests, calls the appropriate tools if needed, executes functions needed, returns response to LLM and returns the response to user
def run_agent(user_request):

    #CONTEXT sent to AI
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful task management assistant. "
                "You can add, list, complete and delete tasks using tools. "
                "Use the appropriate tool when the user requests an action. "
                "If the user wants to complete or delete a task but its "
                "number is unclear, list the tasks first. "
                "Never claim an action succeeded unless the tool confirms it. "
                "Use Medium priority if no priority is specified. "
                "Use Not specified if no due date is provided."
            )
        },
        {
            "role": "user",
            "content": user_request
        }
    ]

    # Agent execution loop
    #limit of 5 prevents an endless execution loop - it allows agent to call tools multiple times if needed
    for _ in range(5):

        #send everything to the LLM 
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            tools=tools
        )

        assistant_message = response.message
        #add response to the conversation history
        messages.append(assistant_message)

        # If no tool is needed, return the response
        if not assistant_message.tool_calls:
            return assistant_message.content or "No response."

        # Execute the requested tools
        for call in assistant_message.tool_calls:

            name = call.function.name
            arguments = call.function.arguments

            if hasattr(arguments, "model_dump"):
                arguments = arguments.model_dump()

            if name not in available_functions:
                result = "Unknown tool."
            else:
                result = available_functions[name](**arguments)

            # Send tool result back to the LLM
            messages.append({
                "role": "tool",
                "name": name,
                "content": result
            })

    return "Maximum number of steps reached. Please try again."

#interface with Streamlit 
#Load tasks to calculate the statistics displayed on the dashboard.
tasks = load_tasks()

total = len(tasks)
completed = sum(1 for task in tasks if task["done"])
pending = total - completed

# Task statistics
col1, col2, col3 = st.columns(3)

col1.metric("Total tasks", total)
col2.metric("Pending", pending)
col3.metric("Completed", completed)

st.divider()

# conversation
if "conversation" not in st.session_state:
    st.session_state.conversation = []

for item in st.session_state.conversation:
    with st.chat_message(item["role"]):
        st.write(item["content"])
# Input
prompt = st.chat_input(
    "Ex: Add buy milk with high priority for tomorrow"
)

if prompt:
    #save user input to conversation history
    st.session_state.conversation.append({
        "role": "user",
        "content": prompt
    })
    #display user input
    with st.chat_message("user"):
        st.write(prompt)
    #run agent to process the user input and generate a response
    with st.chat_message("assistant"):

        with st.spinner("AI Agent is working..."):

            try:
                answer = run_agent(prompt)

            except Exception as error:
                answer = (
                    "Could not connect to Ollama or execute the tool. "
                    f"Error: {error}"
                )

            st.write(answer)
    #save AI response to conversation history
    st.session_state.conversation.append({
        "role": "assistant",
        "content": answer
    })

    st.rerun()




# Display tasks with filtering options using streamlit

st.subheader("My Tasks")

filter_option = st.selectbox(
    "Filter tasks",
    ["All", "Pending", "Completed"]
)

tasks = load_tasks()

if filter_option == "Pending":
    displayed_tasks = [
        (i, task) for i, task in enumerate(tasks)
        if not task["done"]
    ]
elif filter_option == "Completed":
    displayed_tasks = [
        (i, task) for i, task in enumerate(tasks)
        if task["done"]
    ]
else:
    displayed_tasks = list(enumerate(tasks))

if not displayed_tasks:
    st.info("No tasks to display.")

for index, task in displayed_tasks:

    status = "Completed" if task["done"] else "Pending"

    with st.expander(f"{index + 1}. {task['title']}"):

        st.write(f"**Priority:** {task['priority']}")
        st.write(f"**Due date:** {task['due_date']}")
        st.write(f"**Status:** {status}")

        if not task["done"]:
            if st.button("Mark as completed", key=f"complete_{index}"):
                complete_task(index + 1)
                st.rerun()

        if st.button("Delete task", key=f"delete_{index}"):
            delete_task(index + 1)
            st.rerun()


# Clear chat history (doesnt clear json file only removes conversarion from interface
if st.button("Clear conversation"):
    st.session_state.conversation = []
    st.rerun()
