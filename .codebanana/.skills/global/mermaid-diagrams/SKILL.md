---
name: mermaid-diagrams
description: |
  Mermaid diagram generation guide: create flowcharts, sequence diagrams, architecture visualizations directly in response text.
  Triggers:
  - "diagram", "flowchart", "visualization", "architecture diagram"
  - "draw a diagram", "create flowchart", "visualize workflow"
  - "sequence diagram", "ER diagram", "class diagram"
  - User asks to visualize logic or architecture
---

# Mermaid Diagram Guide

## When to Use

- User requests workflow / architecture visualization
- Complex logic needs visual explanation
- User mentions "diagram", "flowchart", "visualization"

## How to Generate

When user asks for a diagram/flowchart/visualization, you MUST include the complete Mermaid code in the SAME response.

### Output Rules

- Include Mermaid code directly in your response text
- Wrap with ` ```mermaid ` code blocks
- No tool calls needed for diagram generation
- Provide a brief explanation alongside the diagram
