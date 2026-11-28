import { useQuery } from '@tanstack/react-query'

import { authApi } from '@/api/auth'

/**
 * How sign-in codes reach people: texted by RentFlow ('sms') or handed over by
 * a landlord or caretaker ('manual'). Until the answer arrives the screens
 * assume 'sms', which is the wording that was always there.
 */
export function useAuthConfig() {
  const config = useQuery({
    queryKey: ['auth-config'],
    queryFn: authApi.config,
    staleTime: 10 * 60 * 1000,
    retry: false,
  })
  return { otpDelivery: config.data?.otp_delivery ?? 'sms', isLoaded: config.isSuccess }
}
