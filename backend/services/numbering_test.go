package services

import (
	"errors"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"
	"gorm.io/gorm"
)

func TestCreateWithRetry_RetriesOnDuplicateKey(t *testing.T) {
	var assigned []string
	attempts := 0
	err := createWithRetry(
		func(offset int64) (string, error) { return fmt.Sprintf("QT-20260101-%03d", 1+offset), nil },
		func(n string) { assigned = append(assigned, n) },
		func() error {
			attempts++
			if attempts < 3 {
				return errors.New(`ERROR: duplicate key value violates unique constraint "idx_quotations_quotation_number" (SQLSTATE 23505)`)
			}
			return nil
		},
	)
	assert.NoError(t, err)
	assert.Equal(t, []string{"QT-20260101-001", "QT-20260101-002", "QT-20260101-003"}, assigned)
}

func TestCreateWithRetry_GivesUpAfterMaxRetries(t *testing.T) {
	attempts := 0
	err := createWithRetry(
		func(offset int64) (string, error) { return "x", nil },
		func(string) {},
		func() error { attempts++; return gorm.ErrDuplicatedKey },
	)
	assert.ErrorIs(t, err, gorm.ErrDuplicatedKey)
	assert.Equal(t, maxNumberRetries, attempts)
}

func TestCreateWithRetry_DoesNotRetryOtherErrors(t *testing.T) {
	attempts := 0
	err := createWithRetry(
		func(offset int64) (string, error) { return "x", nil },
		func(string) {},
		func() error { attempts++; return errors.New("connection refused") },
	)
	assert.EqualError(t, err, "connection refused")
	assert.Equal(t, 1, attempts)
}

func TestIsDuplicateKey(t *testing.T) {
	assert.True(t, isDuplicateKey(gorm.ErrDuplicatedKey))
	assert.True(t, isDuplicateKey(errors.New("SQLSTATE 23505")))
	assert.False(t, isDuplicateKey(errors.New("timeout")))
	assert.False(t, isDuplicateKey(nil))
}
