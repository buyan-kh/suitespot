'use client';

import { useState } from 'react';
import { CreditCard, Lock, ShieldCheck } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';

export type CardDetails = {
  cardholderName: string;
  cardNumber: string;
  expiry: string;
  cvc: string;
  postalCode: string;
};

type CardEntryFormProps = {
  totalAmount: number;
  onSubmit: (details: CardDetails) => Promise<void>;
  isLoading: boolean;
  errorMessage?: string;
};

export default function CardEntryForm({
  totalAmount,
  onSubmit,
  isLoading,
  errorMessage,
}: CardEntryFormProps) {
  const [details, setDetails] = useState<CardDetails>({
    cardholderName: '',
    cardNumber: '',
    expiry: '',
    cvc: '',
    postalCode: '',
  });

  const [errors, setErrors] = useState<Partial<Record<keyof CardDetails, string>>>({});

  const handleCardNumberChange = (value: string) => {
    const raw = value.replace(/\D/g, '').slice(0, 16);
    const formatted = raw.match(/.{1,4}/g)?.join(' ') || raw;
    setDetails((prev) => ({ ...prev, cardNumber: formatted }));
    if (errors.cardNumber) setErrors((prev) => ({ ...prev, cardNumber: undefined }));
  };

  const handleExpiryChange = (value: string) => {
    const raw = value.replace(/\D/g, '').slice(0, 4);
    let formatted = raw;
    if (raw.length >= 3) {
      formatted = `${raw.slice(0, 2)}/${raw.slice(2, 4)}`;
    }
    setDetails((prev) => ({ ...prev, expiry: formatted }));
    if (errors.expiry) setErrors((prev) => ({ ...prev, expiry: undefined }));
  };

  const handleCvcChange = (value: string) => {
    const raw = value.replace(/\D/g, '').slice(0, 4);
    setDetails((prev) => ({ ...prev, cvc: raw }));
    if (errors.cvc) setErrors((prev) => ({ ...prev, cvc: undefined }));
  };

  const validate = (): boolean => {
    const nextErrors: Partial<Record<keyof CardDetails, string>> = {};
    const digitsOnlyCard = details.cardNumber.replace(/\s/g, '');

    if (!details.cardholderName.trim()) {
      nextErrors.cardholderName = 'Enter name on card.';
    }
    if (digitsOnlyCard.length < 15) {
      nextErrors.cardNumber = 'Enter a valid 16-digit card number.';
    }
    if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(details.expiry)) {
      nextErrors.expiry = 'Valid MM/YY required.';
    }
    if (details.cvc.length < 3) {
      nextErrors.cvc = 'Enter 3 or 4 digit CVC.';
    }
    if (!details.postalCode.trim()) {
      nextErrors.postalCode = 'Enter ZIP / Postal code.';
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    await onSubmit(details);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {errorMessage && (
        <div className="p-3 text-sm text-danger bg-danger-soft border border-danger/20 rounded-control">
          {errorMessage}
        </div>
      )}

      <div className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-xs font-bold text-muted uppercase tracking-wider">
            Cardholder Name
          </label>
          <Input
            placeholder="Jane Doe"
            value={details.cardholderName}
            onChange={(e) => {
              setDetails((prev) => ({ ...prev, cardholderName: e.target.value }));
              if (errors.cardholderName) setErrors((prev) => ({ ...prev, cardholderName: undefined }));
            }}
            aria-invalid={!!errors.cardholderName}
          />
          {errors.cardholderName && (
            <p className="text-xs text-danger">{errors.cardholderName}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="flex justify-between items-center">
            <label className="text-xs font-bold text-muted uppercase tracking-wider">
              Card Number
            </label>
            <div className="flex items-center gap-1.5 text-xs text-muted">
              <Lock className="w-3.5 h-3.5" /> 256-bit encrypted
            </div>
          </div>
          <div className="relative">
            <Input
              placeholder="4000 1234 5678 9010"
              value={details.cardNumber}
              onChange={(e) => handleCardNumberChange(e.target.value)}
              aria-invalid={!!errors.cardNumber}
              className="pr-10"
            />
            <CreditCard className="w-5 h-5 text-muted absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
          {errors.cardNumber && (
            <p className="text-xs text-danger">{errors.cardNumber}</p>
          )}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-muted uppercase tracking-wider">
              Expires
            </label>
            <Input
              placeholder="MM/YY"
              value={details.expiry}
              onChange={(e) => handleExpiryChange(e.target.value)}
              aria-invalid={!!errors.expiry}
            />
            {errors.expiry && <p className="text-xs text-danger">{errors.expiry}</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-muted uppercase tracking-wider">
              CVC
            </label>
            <Input
              placeholder="123"
              value={details.cvc}
              onChange={(e) => handleCvcChange(e.target.value)}
              aria-invalid={!!errors.cvc}
            />
            {errors.cvc && <p className="text-xs text-danger">{errors.cvc}</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-muted uppercase tracking-wider">
              ZIP Code
            </label>
            <Input
              placeholder="95113"
              value={details.postalCode}
              onChange={(e) => {
                setDetails((prev) => ({ ...prev, postalCode: e.target.value }));
                if (errors.postalCode) setErrors((prev) => ({ ...prev, postalCode: undefined }));
              }}
              aria-invalid={!!errors.postalCode}
            />
            {errors.postalCode && <p className="text-xs text-danger">{errors.postalCode}</p>}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted pt-1">
        <ShieldCheck className="w-4 h-4 text-success shrink-0" />
        <span>Payments are securely processed via tokenized sandbox gateway.</span>
      </div>

      <Button type="submit" disabled={isLoading} className="w-full h-12 text-base font-bold">
        {isLoading ? 'Processing payment…' : `Pay $${totalAmount.toFixed(2)}`}
      </Button>
    </form>
  );
}