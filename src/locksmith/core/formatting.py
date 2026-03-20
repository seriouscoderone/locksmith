# -*- encoding: utf-8 -*-
"""
archie.core.formatting module

This module contains code for formatting in the Archimedes UI.

"""
from dataclasses import dataclass


@dataclass
class ToDoItem:
    id: int
    title: str
    status: str
    description: str

    @classmethod
    def from_json(cls, data):
        return cls(
            id=data["id"],
            title=data["title"],
            status=data["status"],
            description=data["description"],
        )

@dataclass
class TodoList:
    goal: str
    items: list[ToDoItem]

    @classmethod
    def from_json(cls, data):
        return cls(
            goal=data["goal"],
            items=[ToDoItem.from_json(item) for item in data["items"]]
        )


def format_todo_list_as_markdown(
        todo_list: TodoList, review=False, initial_divider=False
) -> str:
    """Format a to-do list as markdown with progress bar and status indicators."""
    # Move formatting for individual to-do items into here
    goal = todo_list.goal
    todo_items = todo_list.items
    markdown_output = []

    # Header with goal
    if initial_divider:
        markdown_output.append("---")
    markdown_output.append(
        "## Todo List Overview" if not review else "## Todo List Review"
    )
    markdown_output.append("")
    markdown_output.append(f"**Goal:** {goal}")
    markdown_output.append("")

    # Progress bar
    blocked_progress_message = ""
    status_counts = {
        "pending": 0,
        "in_progress": 0,
        "awaiting_input": 0,
        "completed": 0,
        "blocked": 0,
    }
    for idx, item in enumerate(todo_items):
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        if item.status == "blocked":
            blocked_progress_message = f". __Item {idx+1}__ was blocked by the user."

    total_items = len(todo_items)
    completed = status_counts["completed"]
    progress_percentage = int((completed / total_items) * 100) if total_items > 0 else 0
    progress_bar = "█" * (progress_percentage // 10) + "░" * (
            10 - (progress_percentage // 10)
    )

    markdown_output.append(
        f"**Progress:** {completed}/{total_items} completed ({progress_percentage}%){blocked_progress_message}"
    )
    markdown_output.append("```")
    markdown_output.append(f"[{progress_bar}] {progress_percentage}%")
    markdown_output.append("```")
    markdown_output.append("---")

    # Task list with status-based formatting
    for i, item in enumerate(todo_items, 1):
        if item.status == "completed":
            # Checkmark for completed items
            markdown_output.append(f"✓ {i}. {item.title}\n\n")
        elif item.status == "in_progress":
            # Arrow for current item
            markdown_output.append(f"__→ {i}. {item.title} [In Progress]__\n\n")
        elif item.status == "blocked":
            # X for blocked items
            markdown_output.append(f"__X {i}. {item.title} [Blocked]__\n\n")
        elif item.status == "awaiting_input":
            # Question mark for items awaiting input
            markdown_output.append(f"__? {i}. {item.title} [Awaiting Input]__\n\n")
        else:  # pending
            # Bullet for pending items
            markdown_output.append(f"• {i}. {item.title}\n\n")

        if item.description:
            markdown_output.append(f"Description: {item.description}\n\n")

        if i < len(todo_items) or review:
            markdown_output.append("----\n\n")

    return "\n".join(markdown_output)
