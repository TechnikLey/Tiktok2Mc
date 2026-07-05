# Actions & Minecraft

This chapter describes how TikTok events are translated into Minecraft actions. It covers `actions.mca`, the Event-Command-Mapper, RCON, and the overlay system.

## Two Levels of Action Execution

| Level | Description | Target Audience |
|-------|--------------|------------|
| **actions.mca** | Direct, user-configurable mapping of events to actions | End users |
| **Event-Command-Mapper** | Programmatic loose coupling between components via EventBus | Plugin developers |

Both can be used in parallel. The `actions.mca` is intended for simple, direct actions, while the Event-Command-Mapper is for complex workflows between plugins.

## Chapter Structure

1. [Actions.mca Reference](./ch05-01-actions-mca-overview.md) – Format, action types, comments
2. [Event-Command-Mapper](./ch05-02-event-command-mapper.md) – Loose coupling between plugins
3. [RCON & Minecraft](./ch05-03-rcon-and-minecraft.md) – Connection to the Minecraft server
4. [Overlay System](./ch05-04-overlay-system.md) – Text and graphics in the live stream
