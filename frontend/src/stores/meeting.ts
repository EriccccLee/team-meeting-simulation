import { ref } from 'vue'
import { defineStore } from 'pinia'

export interface Participant {
  slug: string
  name: string
  color: string
}

export const useMeetingStore = defineStore('meeting', () => {
  const participants = ref<Participant[]>([])
  const topic = ref('')
  const loaded = ref(false)

  async function fetchParticipants(): Promise<void> {
    if (loaded.value && participants.value.length > 0) return
    const res = await fetch('/api/participants')
    if (res.ok) {
      participants.value = await res.json()
    }
    loaded.value = true
  }

  function colorOf(slug: string): string {
    return participants.value.find(p => p.slug === slug)?.color ?? '#999'
  }

  function nameOf(slug: string): string {
    return participants.value.find(p => p.slug === slug)?.name ?? slug
  }

  return { participants, topic, loaded, fetchParticipants, colorOf, nameOf }
})
