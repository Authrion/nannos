import { LogOut } from 'lucide-react';
import { config } from '../config';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';

/**
 * Public confirmation page shown after a successful logout.
 *
 * Crucially this is NOT a protected route and does NOT auto-trigger login,
 * so the user actually sees that they have been logged out instead of being
 * silently re-authenticated. Logging back in is an explicit user action.
 */
export function LoggedOutPage() {
  const handleLogin = () => {
    window.location.href = `${config.apiBaseUrl}/api/v1/auth/login?redirectTo=${encodeURIComponent(
      window.location.origin + '/app'
    )}`;
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <LogOut className="h-6 w-6 text-muted-foreground" />
          </div>
          <CardTitle>You've been logged out</CardTitle>
          <CardDescription>Your session has ended. You can safely close this tab.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleLogin} className="w-full">
            Log back in
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
